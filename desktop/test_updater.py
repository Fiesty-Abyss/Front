"""Generate throwaway signing/TLS keys, run official Rust updater tests, never install anything."""
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def run(root: Path, transport_only=False):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    root=root.resolve();root.mkdir(parents=True,exist_ok=False)
    project=Path(__file__).resolve().parents[1]
    node=shutil.which('node');assert node
    cli=project/'desktop/node_modules/@tauri-apps/cli/tauri.js'
    def signer(*args):
        result=subprocess.run([node,str(cli),'signer',*args],capture_output=True,text=True,timeout=30)
        if result.returncode:raise RuntimeError('official Tauri signer failed; captured output is not printed to protect key material')
    signer('generate','--ci','-p','','-w',str(root/'throwaway.key'))
    signer('generate','--ci','-p','','-w',str(root/'other.key'))
    payload=(b'Front generated signed updater fixture. Not an installer.\n'*20000)
    (root/'payload').write_bytes(payload)
    signer('sign','-f',str(root/'throwaway.key'),'-p','','--app-version','9.9.0',str(root/'payload'))
    now=datetime.now(timezone.utc)
    ca_key=ec.generate_private_key(ec.SECP256R1());server_key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Front generated test CA')])
    ca=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,data_encipherment=False,
            key_agreement=False,key_cert_sign=True,crl_sign=True,encipher_only=False,decipher_only=False),critical=True).sign(ca_key,hashes.SHA256()))
    leaf=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Front loopback test')]))
        .issuer_name(name).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,data_encipherment=False,
            key_agreement=False,key_cert_sign=False,crl_sign=False,encipher_only=False,decipher_only=False),critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False).sign(ca_key,hashes.SHA256()))
    (root/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (root/'server.pem').write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    (root/'server-key.pem').write_bytes(server_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    signature=(root/'payload.sig').read_text().strip()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/latest.json':
                body=json.dumps({'version':'9.9.0','notes':'Generated test release; no installation',
                    'platforms':{'windows-x86_64':{'url':base+'/package','signature':signature}},
                    'front':{'channel':'preview','backup_format':1,'minimum_source_version':'0.1.0'}}).encode()
            elif self.path=='/package':body=payload
            elif self.path=='/tampered':body=b'X'+payload[1:]
            else:self.send_response(404);self.end_headers();return
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except OSError:pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(root/'server.pem',root/'server-key.pem')
    server.socket=context.wrap_socket(server.socket,server_side=True)
    base='https://127.0.0.1:'+str(server.server_address[1]);(root/'source.txt').write_text(base)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        if transport_only:
            import urllib.request
            with urllib.request.urlopen(base+'/package',context=ssl.create_default_context(cafile=str(root/'ca.pem')),timeout=5) as response:
                assert response.read()==payload
            print(json.dumps({'fixture':'generated','official_signer':'signing completed','python_https':'passed','rust_sdk_tests':'not run','installation_executed':False}))
            return
        env={**os.environ,'FRONT_UPDATER_TEST_ROOT':str(root)}
        cargo=shutil.which('cargo') or env.get('FRONT_CARGO');assert cargo
        subprocess.run([cargo,'test','--release','--locked','--manifest-path',str(project/'desktop/src-tauri/Cargo.toml'),
            'updater_tests','--','--include-ignored'],env=env,check=True,timeout=900)
    finally:server.shutdown();server.server_close();worker.join(timeout=5)
    print(json.dumps({'fixture':'generated','signer':'official Tauri CLI','transport':'loopback HTTPS with test CA, no OS trust changes','installation_executed':False,'rust_tests':'passed'}))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('new_fixture_root',type=Path);parser.add_argument('--transport-only',action='store_true')
    args=parser.parse_args();run(args.new_fixture_root,args.transport_only)
