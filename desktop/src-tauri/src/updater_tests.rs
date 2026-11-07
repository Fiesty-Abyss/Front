use super::updates::*;
use tauri::Manager;
use tauri_plugin_updater::{Updater,UpdaterExt};
use serde_json::json;
use std::{fs,path::PathBuf,time::Duration};

fn root()->PathBuf{std::env::var_os("FRONT_UPDATER_TEST_ROOT").map(PathBuf::from).expect("run python desktop/test_updater.py with a new isolated fixture root")}
fn updater(key_name:&str,trust_fixture_ca:bool)->Updater{
    updater_at(key_name,trust_fixture_ca,"/latest.json")
}
fn updater_at(key_name:&str,trust_fixture_ca:bool,manifest:&str)->Updater{
    let folder=root();let key=fs::read_to_string(folder.join(key_name)).unwrap();
    let mut context=tauri::test::mock_context(tauri::test::noop_assets());
    context.config_mut().plugins.0.insert("updater".into(),json!({"pubkey":key,"requireSignedVersion":true}));
    let app=tauri::test::mock_builder().plugin(tauri_plugin_updater::Builder::new().build()).build(context).unwrap();
    let source=fs::read_to_string(folder.join("source.txt")).unwrap();
    let mut builder=app.updater_builder().target("windows-x86_64").no_proxy().timeout(Duration::from_secs(5))
        .endpoints(vec![format!("{source}{manifest}").parse().unwrap()]).unwrap();
    if trust_fixture_ca{
        let cert=reqwest::Certificate::from_pem(&fs::read(folder.join("ca.pem")).unwrap()).unwrap();
        builder=builder.configure_client(move|client|client.add_root_certificate(cert.clone()));
    }
    builder.build().unwrap()
}

#[test]
#[ignore="isolated real signing/HTTPS fixture: python desktop/test_updater.py"]
fn updater_tests_real_sdk_downgrade_interruption_and_cancel(){
    tauri::async_runtime::block_on(async{
        assert!(updater_at("throwaway.key.pub",true,"/downgrade.json").check().await.unwrap().is_none());
        let engine=updater("throwaway.key.pub",true);let release=engine.check().await.unwrap().unwrap();
        let source=fs::read_to_string(root().join("source.txt")).unwrap();
        let mut raw=release.raw_json.clone();raw["platforms"]["windows-x86_64"]["url"]=json!(format!("{source}/interrupted"));
        let interrupted=engine.restore_update(raw).unwrap().unwrap();
        assert!(interrupted.download(|_,_|{},||{}).await.is_err(),"truncated TLS transfer must not produce an installable payload");
        let mut raw=release.raw_json.clone();raw["platforms"]["windows-x86_64"]["url"]=json!(format!("{source}/slow"));
        let slow=engine.restore_update(raw).unwrap().unwrap();
        use std::sync::{Arc,atomic::{AtomicBool,Ordering}};
        use futures_util::future::{AbortHandle,Abortable,join};
        let seen=Arc::new(AtomicBool::new(false));let completed=Arc::new(AtomicBool::new(false));
        let progress=seen.clone();let finished=completed.clone();
        let(handle,registration)=AbortHandle::new_pair();
        let downloading=Abortable::new(slow.download(move|n,_|{if n>0{progress.store(true,Ordering::SeqCst);}},move||{finished.store(true,Ordering::SeqCst);}),registration);
        let cancellation=async{
            let deadline=std::time::Instant::now()+Duration::from_secs(10);
            while !seen.load(Ordering::SeqCst){
                assert!(std::time::Instant::now()<deadline,"download never reached a real progress callback");
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
            handle.abort();
        };
        let(result,_)=join(downloading,cancellation).await;
        assert!(result.is_err());assert!(!completed.load(Ordering::SeqCst));
    });
}

#[test]
#[ignore="isolated real signing/HTTPS fixture: python desktop/test_updater.py"]
fn updater_tests_generated_manifest_compatibility_and_channels(){
    tauri::async_runtime::block_on(async{
        let engine=updater("throwaway.key.pub",true);let local=engine.check().await.unwrap().unwrap();
        assert!(validate(&local,"preview","windows-x86_64").is_err(),"production validation must never admit the local test transport");
        let mut raw=local.raw_json.clone();
        raw["front"]["minimum_source_version"]=json!(local.current_version.clone());
        // Parsed by the real SDK; this generated URL is never fetched or installed.
        raw["platforms"]["windows-x86_64"]["url"]=json!("https://github.com/Fiesty-Abyss/Front/releases/download/v9.9.0/generated-unused.exe");
        let trusted=engine.restore_update(raw.clone()).unwrap().unwrap();
        assert!(validate(&trusted,"preview","windows-x86_64").is_ok());
        assert!(validate(&trusted,"stable","windows-x86_64").is_err());
        assert!(validate(&trusted,"preview","windows-x86_64-portable").is_err());
        for (field,value) in [("backup_format",json!(99)),("minimum_source_version",json!("999.0.0")),("channel",json!("other"))]{
            let mut wrong=raw.clone();wrong["front"][field]=value;
            assert!(validate(&engine.restore_update(wrong).unwrap().unwrap(),"preview","windows-x86_64").is_err());
        }
        raw["version"]=json!("9.9.1-rc.1");raw["front"]["channel"]=json!("stable");
        assert!(validate(&engine.restore_update(raw).unwrap().unwrap(),"stable","windows-x86_64").is_err());
    });
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
