//! Official updater behind one narrowly scoped command. No arbitrary endpoints, paths or shell commands.
use std::{fs, io::{Read,Write}, path::{Path,PathBuf}, sync::{Arc,Mutex,atomic::{AtomicBool,AtomicU64,Ordering}},time::{Duration,SystemTime,UNIX_EPOCH}};
use futures_util::future::{AbortHandle,AbortRegistration,Abortable};
use serde::{Deserialize,Serialize};
use tauri::Manager;
use tauri_plugin_updater::{Update,UpdaterExt};

const MAX_BYTES:u64=256*1024*1024;
const TERMINAL:&[&str]=&["done","error","cancelled","interrupted"];
fn epoch()->u64{SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs()}

#[derive(Clone,Default,Serialize,Deserialize)]
struct Preferences{channel:String,defer_until:u64,last_error:Option<String>}
#[derive(Clone,Serialize)]
pub struct View{
    enabled:bool,version:String,portable:bool,channel:String,phase:String,
    available_version:Option<String>,notes:Option<String>,downloaded:u64,total:Option<u64>,
    saved_filename:Option<String>,error:Option<String>,deferred:bool,
    backup_done:u64,backup_total:u64,
}
pub struct Updates{
    folder:PathBuf,origin:String,key:Option<String>,
    view:Arc<Mutex<View>>,prefs:Mutex<Preferences>,update:Mutex<Option<Update>>,
    saved:Mutex<Option<PathBuf>>,busy:AtomicBool,cancel:Mutex<Option<AbortHandle>>,
    stopped:Arc<AtomicBool>,
    sequence:AtomicU64,
}
impl Updates{
    pub fn new(folder:PathBuf,origin:String,version:String)->Result<Self,Box<dyn std::error::Error>>{
        let key=option_env!("FRONT_UPDATE_PUBLIC_KEY").filter(|v|!v.trim().is_empty()).map(str::to_owned);
        let portable=std::env::current_exe()?.parent().is_some_and(|p|p.join("Front.portable").is_file());
        let prefs_path=folder.join("desktop-updates.json");
        let mut prefs:Preferences=prefs_path.metadata().ok().filter(|m|m.len()<8192)
            .and_then(|_|fs::read(&prefs_path).ok()).and_then(|v|serde_json::from_slice(&v).ok()).unwrap_or_default();
        if prefs.channel!="preview"{prefs.channel="stable".into();}
        let view=View{enabled:key.is_some()&&cfg!(all(windows,target_arch="x86_64")),version,portable,
            channel:prefs.channel.clone(),phase:"idle".into(),available_version:None,notes:None,
            downloaded:0,total:None,saved_filename:None,error:prefs.last_error.clone(),deferred:prefs.defer_until>epoch(),backup_done:0,backup_total:0};
        Ok(Self{folder,origin,key,view:Arc::new(Mutex::new(view)),prefs:Mutex::new(prefs),
            update:Mutex::new(None),saved:Mutex::new(None),busy:AtomicBool::new(false),
            cancel:Mutex::new(None),stopped:Arc::new(AtomicBool::new(false)),sequence:AtomicU64::new(0)})
    }
    fn snapshot(&self)->View{self.view.lock().unwrap().clone()}
    fn phase(&self,phase:&str){self.view.lock().unwrap().phase=phase.into();}
    fn persist(&self)->Result<(),String>{atomic_file(&self.folder,"desktop-updates.json",&serde_json::to_vec(&*self.prefs.lock().unwrap()).map_err(|_|"update_preferences_failed")?)}
}
struct Busy<'a>(&'a Updates);
impl Drop for Busy<'_>{fn drop(&mut self){let mut handle=self.0.cancel.lock().unwrap();*handle=None;self.0.busy.store(false,Ordering::SeqCst);}}
fn begin_operation(state:&Updates)->Result<AbortRegistration,String>{
    let mut handle=state.cancel.lock().unwrap();
    if state.busy.compare_exchange(false,true,Ordering::SeqCst,Ordering::SeqCst).is_err(){return Err("update_busy".into());}
    let(cancel,registration)=AbortHandle::new_pair();*handle=Some(cancel);Ok(registration)
}

fn atomic_file(folder:&Path,name:&str,bytes:&[u8])->Result<(),String>{
    let temp=folder.join(format!(".update-{}-{}.tmp",std::process::id(),SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos()));
    let mut created=false;
    let work=(||->std::io::Result<()>{let mut f=fs::OpenOptions::new().write(true).create_new(true).open(&temp)?;created=true;f.write_all(bytes)?;f.sync_all()?;drop(f);fs::rename(&temp,folder.join(name))})();
    if work.is_err(){if created{let _=fs::remove_file(temp);}return Err("update_storage_failed".into());}Ok(())
}
fn endpoint(channel:&str)->Result<&'static str,String>{match channel{
    "stable"=>Ok("https://github.com/Fiesty-Abyss/Front/releases/latest/download/latest.json"),
    "preview"=>Ok("https://github.com/Fiesty-Abyss/Front/releases/download/preview/latest.json"),
    _=>Err("update_channel_invalid".into())}}
fn trusted_download(url:&reqwest::Url)->bool{
    url.scheme()=="https"&&url.host_str()==Some("github.com")&&url.port_or_known_default()==Some(443)
        &&url.username().is_empty()&&url.password().is_none()&&url.fragment().is_none()
        &&url.path().starts_with("/Fiesty-Abyss/Front/releases/download/")
}
fn validate(update:&Update,channel:&str,target:&str)->Result<(),String>{
    if !trusted_download(&update.download_url){return Err("update_source_invalid".into());}
    let version=semver::Version::parse(&update.version).map_err(|_|"update_version_invalid")?;
    let current=semver::Version::parse(&update.current_version).map_err(|_|"update_version_invalid")?;
    if version<=current||(channel=="stable"&&!version.pre.is_empty()){return Err("update_version_invalid".into());}
    let metadata=&update.raw_json["front"];
    let minimum=metadata["minimum_source_version"].as_str().and_then(|v|semver::Version::parse(v).ok()).ok_or("update_compatibility_missing")?;
    if metadata["channel"].as_str()!=Some(channel)||metadata["backup_format"].as_u64()!=Some(1)
        ||current<minimum||!update.raw_json["platforms"][target].is_object(){return Err("update_incompatible".into());}
    Ok(())
}
fn service_details(app:&tauri::AppHandle)->Result<(u16,String),String>{
    let state=app.state::<Mutex<Option<super::Service>>>();let service=state.lock().unwrap();
    service.as_ref().map(|s|(s.ready.port,s.ready.token.clone())).ok_or_else(||"update_service_unavailable".into())
}
fn stop_service(app:&tauri::AppHandle){
    let state=app.state::<Mutex<Option<super::Service>>>();let service=state.lock().unwrap().take();
    if let Some(mut service)=service{service.stop();}
}
fn cancel_operation(state:&Updates)->Result<u64,String>{
    let mut handle=state.cancel.lock().unwrap();
    if state.snapshot().phase=="installing"{return Err("update_install_in_progress".into());}
    if !state.busy.load(Ordering::SeqCst){return Err("update_not_running".into());}
    let sequence=state.sequence.load(Ordering::SeqCst);
    if let Some(handle)=handle.take(){handle.abort();}Ok(sequence)
}
fn commit_install(state:&Updates)->bool{
    let handle=state.cancel.lock().unwrap();
    if handle.is_none(){return false;}
    state.phase("installing");true
}
async fn release(client:&reqwest::Client,base:&str,token:&str,lease:&str){
    let _=client.post(format!("{base}/_desktop/update/release")).bearer_auth(token).header("x-front-update-request",lease).send().await;
}
async fn release_preparation(app:&tauri::AppHandle,sequence:u64){
    if sequence==0{return;}
    if let Ok((port,token))=service_details(app){
        if let Ok(client)=reqwest::Client::builder().no_proxy().timeout(Duration::from_secs(3)).build(){
            release(&client,&format!("http://127.0.0.1:{port}"),&token,&sequence.to_string()).await;
        }
    }
}
async fn backup(app:&tauri::AppHandle,state:&Updates)->Result<(reqwest::Client,String,String,String),String>{
    let(port,token)=service_details(app)?;let base=format!("http://127.0.0.1:{port}");
    let client=reqwest::Client::builder().no_proxy().timeout(Duration::from_secs(15)).build().map_err(|_|"update_backup_failed")?;
    // Known before sending: cancellation still works if the response was lost or arrives late.
    let lease={
        let handle=state.cancel.lock().unwrap();
        if handle.is_none(){return Err("update_cancelled".into());}
        (state.sequence.fetch_add(1,Ordering::SeqCst)+1).to_string()
    };
    let work=async{
        let response=client.post(format!("{base}/_desktop/update/prepare")).bearer_auth(&token)
            .header("x-front-update-request",&lease).send().await.map_err(|_|"update_backup_failed")?;
        if response.status()==reqwest::StatusCode::CONFLICT{
            return Err(if state.cancel.lock().unwrap().is_none(){"update_cancelled"}else{"update_background_busy"}.to_string());
        }
        if !response.status().is_success(){return Err("update_backup_failed".to_string());}
        let value:serde_json::Value=response.json().await.map_err(|_|"update_backup_failed")?;
        let id=value["id"].as_str().ok_or("update_backup_failed")?;
        let start=std::time::Instant::now();
        loop{
            if start.elapsed()>Duration::from_secs(1800){return Err("update_backup_timeout".to_string());}
            let job:serde_json::Value=client.get(format!("{base}/api/jobs/{id}")).bearer_auth(&token).send().await
                .map_err(|_|"update_backup_failed")?.json().await.map_err(|_|"update_backup_failed")?;
            let status=job["status"].as_str().unwrap_or("error");
            {let mut v=state.view.lock().unwrap();v.backup_done=job["done"].as_u64().unwrap_or(0);v.backup_total=job["total"].as_u64().unwrap_or(0);}
            if TERMINAL.contains(&status){
                if status=="done"&&job["result"]["status"].as_str()==Some("complete")
                    &&job["result"]["verified"]==true&&job["result"]["restore_verified"]==true{return Ok(());}
                return Err("update_backup_failed".to_string());
            }
            if state.cancel.lock().unwrap().as_ref().is_none(){return Err("update_cancelled".to_string());}
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
    }.await;
    if let Err(error)=work{release(&client,&base,&token,&lease).await;return Err(error);}
    Ok((client,base,token,lease))
}

#[tauri::command]
pub async fn desktop_update(app:tauri::AppHandle,window:tauri::WebviewWindow,action:String,channel:Option<String>)->Result<View,String>{
    let state=app.state::<Updates>();
    if window.label()!="main"||window.url().map_err(|_|"update_origin_denied")?.origin().ascii_serialization()!=state.origin{return Err("update_origin_denied".into());}
    if action=="status"{return Ok(state.snapshot());}
    if action=="cancel"{let sequence=cancel_operation(&state)?;release_preparation(&app,sequence).await;return Ok(state.snapshot());}
    let registration=begin_operation(&state)?;
    let _busy=Busy(&state);
    let result=perform(&app,&state,&action,channel,registration).await;
    if let Err(error)=result{let mut view=state.view.lock().unwrap();view.phase="failed".into();view.error=Some(error);}
    Ok(state.snapshot())
}
async fn perform(app:&tauri::AppHandle,state:&Updates,action:&str,channel:Option<String>,registration:AbortRegistration)->Result<(),String>{
    if state.cancel.lock().unwrap().is_none(){return Err("update_cancelled".into());}
    if action=="defer"{
        // Busy remains owned until cleanup returns; a newer operation cannot advance this sequence.
        let sequence=state.sequence.load(Ordering::SeqCst);release_preparation(app,sequence).await;
        if state.cancel.lock().unwrap().is_none(){return Err("update_cancelled".into());}
        state.prefs.lock().unwrap().defer_until=epoch()+86400;state.persist()?;state.view.lock().unwrap().deferred=true;return Ok(());
    }
    if !state.snapshot().enabled{return Err("update_not_configured".into());}
    state.view.lock().unwrap().error=None;
    match action{
        "check"=>{
            let channel=channel.unwrap_or_else(||state.prefs.lock().unwrap().channel.clone());let url=endpoint(&channel)?;
            state.phase("checking");*state.update.lock().unwrap()=None;*state.saved.lock().unwrap()=None;
            {let mut v=state.view.lock().unwrap();v.available_version=None;v.notes=None;v.saved_filename=None;v.channel=channel.clone();v.deferred=false;}
            {let mut prefs=state.prefs.lock().unwrap();prefs.channel=channel.clone();prefs.defer_until=0;prefs.last_error=None;}state.persist()?;
            let target=if state.snapshot().portable{"windows-x86_64-portable"}else{"windows-x86_64"};
            let stopped=state.stopped.clone();let owned_app=app.clone();
            let updater=app.updater_builder().pubkey(state.key.as_ref().unwrap()).target(target)
                .endpoints(vec![url.parse().map_err(|_|"update_source_invalid")?]).map_err(|_|"update_source_invalid")?
                .timeout(Duration::from_secs(20)).version_comparator(move|current,remote|remote.version>current&&(channel!="stable"||remote.version.pre.is_empty()))
                .on_before_exit(move||{stopped.store(true,Ordering::SeqCst);stop_service(&owned_app);}).build().map_err(|_|"update_check_failed")?;
            let update=Abortable::new(updater.check(),registration).await.map_err(|_|"update_cancelled")?.map_err(|_|"update_check_failed")?;
            if let Some(update)=update{
                let channel=state.snapshot().channel;validate(&update,&channel,target)?;
                {let mut v=state.view.lock().unwrap();v.available_version=Some(update.version.clone());v.notes=update.body.clone();v.phase="available".into();}
                *state.update.lock().unwrap()=Some(update);
            }else{state.phase("current");}
        },
        "download"=>{
            let update=state.update.lock().unwrap().clone().ok_or("update_check_required")?;
            let handle=state.cancel.lock().unwrap().clone().ok_or("update_cancelled")?;
            state.phase("downloading");{let mut v=state.view.lock().unwrap();v.downloaded=0;v.total=None;}
            let progress=state.view.clone();let finish=state.view.clone();
            let bytes=Abortable::new(update.download(move|n,total|{
                let mut v=progress.lock().unwrap();v.downloaded+=n as u64;v.total=total;
                if v.downloaded>MAX_BYTES||total.is_some_and(|n|n>MAX_BYTES){v.error=Some("update_too_large".into());handle.abort();}
            },move||{finish.lock().unwrap().phase="verifying".into();}),registration).await
                .map_err(|_|state.snapshot().error.unwrap_or_else(||"update_cancelled".into()))?
                .map_err(|_|"update_signature_or_download_failed")?;
            if bytes.len() as u64>MAX_BYTES{return Err("update_too_large".into());}
            if state.cancel.lock().unwrap().is_none(){return Err("update_cancelled".into());}
            let folder=state.folder.join("updates");fs::create_dir_all(&folder).map_err(|_|"update_storage_failed")?;
            if !folder.canonicalize().map_err(|_|"update_storage_failed")?.starts_with(state.folder.canonicalize().map_err(|_|"update_storage_failed")?){return Err("update_storage_failed".into());}
            let name=format!("Front-{}-{}.{ext}",update.version,epoch(),ext=if state.snapshot().portable{"zip"}else{"exe"});
            atomic_file(&folder,&name,&bytes)?;*state.saved.lock().unwrap()=Some(folder.join(&name));
            {let mut v=state.view.lock().unwrap();v.phase="ready".into();v.saved_filename=Some(name);}
        },
        "install"=>{
            if state.snapshot().portable{return Err("update_portable_manual".into());}
            state.phase("verifying");
            let update=state.update.lock().unwrap().clone().ok_or("update_check_required")?;
            let path=state.saved.lock().unwrap().clone().ok_or("update_download_required")?;
            if path.metadata().map_err(|_|"update_storage_failed")?.len()>MAX_BYTES{return Err("update_too_large".into());}
            let mut bytes=Vec::new();fs::File::open(path).map_err(|_|"update_storage_failed")?.take(MAX_BYTES+1)
                .read_to_end(&mut bytes).map_err(|_|"update_storage_failed")?;
            if bytes.len() as u64>MAX_BYTES{return Err("update_too_large".into());}
            update.verify(&bytes).map_err(|_|"update_signature_or_download_failed")?;
            if state.cancel.lock().unwrap().is_none(){return Err("update_cancelled".into());}
            state.phase("backup");
            let(client,base,token,lease)=backup(app,state).await?;
            if !commit_install(state){release(&client,&base,&token,&lease).await;return Err("update_cancelled".into());}
            state.stopped.store(false,Ordering::SeqCst);
            if update.install(&bytes).is_err(){
                if state.stopped.load(Ordering::SeqCst){state.prefs.lock().unwrap().last_error=Some("update_install_failed_restarted".into());let _=state.persist();app.restart();}
                release(&client,&base,&token,&lease).await;return Err("update_install_failed".into());
            }
        },
        _=>return Err("update_action_invalid".into()),
    }Ok(())
}

#[cfg(test)]
mod updater_tests{
    use super::*;
    #[test]
    fn update_endpoints_and_download_sources_are_fixed(){
        assert!(endpoint("stable").unwrap().starts_with("https://github.com/Fiesty-Abyss/Front/releases/"));
        assert!(endpoint("preview").is_ok());assert!(endpoint("custom").is_err());
        assert!(trusted_download(&"https://github.com/Fiesty-Abyss/Front/releases/download/v9.9.0/installer.exe".parse().unwrap()));
        for url in ["http://github.com/Fiesty-Abyss/Front/releases/download/x/a", "https://evil.example/Fiesty-Abyss/Front/releases/download/x/a", "https://github.com/other/repo/releases/download/x/a", "https://user@github.com/Fiesty-Abyss/Front/releases/download/x/a"]{
            assert!(!trusted_download(&url.parse().unwrap()));
        }
    }
    #[test]
    fn updater_cancellation_and_install_commit_are_mutually_exclusive(){
        for _ in 0..32{
            let state=Updates::new(PathBuf::from(".cache/generated-state-not-created"),"generated".into(),"0.7.0-preview.1".into()).unwrap();
            state.busy.store(true,Ordering::SeqCst);
            state.phase("backup");let(handle,_)=AbortHandle::new_pair();*state.cancel.lock().unwrap()=Some(handle);
            let barrier=std::sync::Barrier::new(2);
            std::thread::scope(|scope|{
                let commit=scope.spawn(||{barrier.wait();commit_install(&state)});
                barrier.wait();let cancelled=cancel_operation(&state).is_ok();
                assert_ne!(commit.join().unwrap(),cancelled,"a successful cancel must never reopen writes after install commit");
            });
        }
    }
    #[test]
    fn updater_cancel_before_cache_verification_cannot_be_reinitialized(){
        let state=Updates::new(PathBuf::from(".cache/generated-state-not-created"),"generated".into(),"0.7.0-preview.1".into()).unwrap();
        let _registration=begin_operation(&state).unwrap();let _busy=Busy(&state);
        state.phase("verifying");assert_eq!(cancel_operation(&state).unwrap(),0);
        assert!(state.cancel.lock().unwrap().is_none());
        state.phase("backup");assert!(!commit_install(&state));
    }
    #[test]
    fn updater_delayed_cancel_keeps_captured_sequence_of_its_own_operation(){
        let state=Updates::new(PathBuf::from(".cache/generated-state-not-created"),"generated".into(),"0.7.0-preview.1".into()).unwrap();
        let _old_registration=begin_operation(&state).unwrap();let old_busy=Busy(&state);
        state.sequence.store(7,Ordering::SeqCst);state.phase("backup");let captured=cancel_operation(&state).unwrap();
        drop(old_busy);
        let _new_registration=begin_operation(&state).unwrap();let _new_busy=Busy(&state);
        state.sequence.store(8,Ordering::SeqCst);state.phase("backup");assert!(commit_install(&state));
        assert_eq!(captured,7);assert_ne!(captured,state.sequence.load(Ordering::SeqCst));
        // Async cleanup receives `captured`, never an Updates reference from which to reread 8.
    }
}
