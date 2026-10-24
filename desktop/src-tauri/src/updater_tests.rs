use super::updates::*;
use tauri::Manager;
use tauri_plugin_updater::{Updater,UpdaterExt};
use serde_json::json;
use std::{fs,path::PathBuf,time::Duration};

fn root()->PathBuf{std::env::var_os("FRONT_UPDATER_TEST_ROOT").map(PathBuf::from).expect("run python desktop/test_updater.py with a new isolated fixture root")}
fn updater(key_name:&str,trust_fixture_ca:bool)->Updater{
    let folder=root();let key=fs::read_to_string(folder.join(key_name)).unwrap();
    let mut context=tauri::test::mock_context(tauri::test::noop_assets());
    context.config_mut().plugins.0.insert("updater".into(),json!({"pubkey":key,"requireSignedVersion":true}));
    let app=tauri::test::mock_builder().plugin(tauri_plugin_updater::Builder::new().build()).build(context).unwrap();
    let source=fs::read_to_string(folder.join("source.txt")).unwrap();
    let mut builder=app.updater_builder().target("windows-x86_64").no_proxy().timeout(Duration::from_secs(5))
        .endpoints(vec![format!("{source}/latest.json").parse().unwrap()]).unwrap();
    if trust_fixture_ca{
        let cert=reqwest::Certificate::from_pem(&fs::read(folder.join("ca.pem")).unwrap()).unwrap();
        builder=builder.configure_client(move|client|client.add_root_certificate(cert.clone()));
    }
    builder.build().unwrap()
}

#[test]
#[ignore="isolated real signing/HTTPS fixture: python desktop/test_updater.py"]
fn updater_tests_real_signed_https_download(){
    tauri::async_runtime::block_on(async{
        let release=updater("throwaway.key.pub",true).check().await.unwrap().unwrap();
        let mut bytes=0;
        let payload=release.download(|n,_|bytes+=n,||{}).await.unwrap();
        assert_eq!(payload,fs::read(root().join("payload")).unwrap());assert_eq!(bytes,payload.len());
        assert!(release.verify(&payload).is_ok());
        let mut tampered=payload.clone();tampered[0]^=1;assert!(release.verify(&tampered).is_err());
        let mut raw=release.raw_json.clone();raw["version"]=json!("9.9.1");
        let replay=updater("throwaway.key.pub",true).restore_update(raw).unwrap().unwrap();
        assert!(replay.verify(&payload).is_err(),"manifest cannot relabel a signed older payload");
        let wrong_key=updater("other.key.pub",true).restore_update(release.raw_json.clone()).unwrap().unwrap();
        assert!(wrong_key.verify(&payload).is_err());
    });
}

#[test]
#[ignore="isolated real signing/HTTPS fixture: python desktop/test_updater.py"]
fn updater_tests_bad_tls_tampered_transfer_and_platform_rejected(){
    tauri::async_runtime::block_on(async{
        assert!(updater("throwaway.key.pub",false).check().await.is_err(),"test CA is never installed system-wide or silently trusted");
        let engine=updater("throwaway.key.pub",true);let release=engine.check().await.unwrap().unwrap();
        let mut raw=release.raw_json.clone();let base=fs::read_to_string(root().join("source.txt")).unwrap();
        raw["platforms"]["windows-x86_64"]["url"]=json!(format!("{base}/tampered"));
        let tampered=engine.restore_update(raw).unwrap().unwrap();assert!(tampered.download(|_,_|{},||{}).await.is_err());
        let mut raw=release.raw_json.clone();raw["platforms"]=json!({"darwin-aarch64":{"url":format!("{base}/package"),"signature":release.signature}});
        assert!(engine.restore_update(raw).is_err(),"wrong target must not fall back to another platform");
    });
}
