#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{fs, io::{BufRead, BufReader, Write}, net::TcpStream, path::{Path, PathBuf}, process::{Child, Command, Stdio}, sync::{mpsc, Arc, Mutex, atomic::{AtomicBool, Ordering}}, time::{Duration, Instant, SystemTime, UNIX_EPOCH}};
use serde::Deserialize;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
mod updates;
#[cfg(test)]
mod updater_tests;
#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[derive(Deserialize)]
struct Ready { port: u16, token: String, pid: u32 }

struct StartupLifecycle(Arc<AtomicBool>);
#[derive(Clone, serde::Serialize)]
struct StartupView { message: &'static str, done: Option<u64>, total: Option<u64>, failed: bool }
#[derive(Default,serde::Serialize)]
struct StartupTimings { process_id:u32, window_created_ms:Option<u64>, service_ready_ms:Option<u64>, document_loaded_ms:Option<u64>,
    display_scale_factor:Option<f64>, initial_inner_width:Option<u32>, initial_inner_height:Option<u32> }
fn record_startup(folder:&Path,timings:&Arc<Mutex<StartupTimings>>,stage:&str,started:Instant) {
    let bytes={
        let mut value=timings.lock().unwrap();let elapsed=started.elapsed().as_millis().min(u64::MAX as u128) as u64;
        match stage {"window"=>value.window_created_ms=Some(elapsed),"service"=>value.service_ready_ms=Some(elapsed),
            "document"=>{if value.document_loaded_ms.is_some(){return;}value.document_loaded_ms=Some(elapsed);},_=>return}
        serde_json::to_vec(&*value).unwrap()
    };
    let logs=folder.join("logs");
    if fs::create_dir_all(&logs).is_err(){return;}
    let (Ok(root),Ok(target))=(folder.canonicalize(),logs.canonicalize())else{return;};
    let file=target.join("native-startup.json");
    if !target.starts_with(root)||fs::symlink_metadata(&file).is_ok_and(|m|m.file_type().is_symlink()){return;}
    // Three bounded writes per launch, numeric stage timings only. Not a TTI signal.
    let _=fs::write(file,bytes);
}

fn local_splash(url:&tauri::Url)->bool {
    url.username().is_empty() && url.password().is_none() && url.port().is_none() &&
        ((url.scheme()=="tauri" && url.host_str()==Some("localhost")) ||
         (url.scheme()=="http" && url.host_str()==Some("tauri.localhost")))
}
fn render_startup(window:&tauri::WebviewWindow, view:&Arc<Mutex<StartupView>>) {
    let data=serde_json::to_string(&*view.lock().unwrap()).unwrap();
    let _=window.eval(format!("if(window.frontStartup) window.frontStartup({data});"));
}
fn progress_message(phase:&str)->Option<&'static str> {
    Some(match phase {
        "checking_data"=>"正在检查资料目录和写入权限…",
        "checking_database"=>"正在检查资料库兼容性…",
        "initializing_database"=>"正在初始化本机资料库…",
        "backup"=>"正在生成升级前完整备份…请勿关闭电源。",
        "verify_backup"=>"正在校验备份中的文件…",
        "restore"=>"正在独立目录验证恢复和迁移…",
        "migrating"=>"正在初始化或安全升级资料库…",
        "starting_service"=>"正在启动本机服务…",
        _=>return None,
    })
}

enum StartupMessage { Progress(&'static str,Option<u64>,Option<u64>,bool), Ready(Ready), Error(&'static str) }
fn startup_message(line:&str, child_pid:u32)->Result<StartupMessage,&'static str> {
    if line.len()>4096 {return Err("sidecar_initialization_failed");}
    let value:serde_json::Value=serde_json::from_str(line).map_err(|_|"sidecar_initialization_failed")?;
    if let Some(phase)=value.get("phase").and_then(|v|v.as_str()) {
        let message=progress_message(phase).ok_or("sidecar_initialization_failed")?;
        let total=value["total"].as_u64().filter(|v|*v>0);
        let done=value["done"].as_u64().filter(|v|total.is_some_and(|n|*v<=n));
        let extended=matches!(phase,"backup"|"verify_backup"|"restore"|"migrating");
        return Ok(StartupMessage::Progress(message,done,total,extended));
    }
    if let Some(code)=value.get("error").and_then(|v|v.as_str()) {
        return Ok(StartupMessage::Error(match code {
            "data_directory_in_use"=>"data_directory_in_use",
            "data_directory_unwritable"=>"data_directory_unwritable",
            "database_incompatible_or_damaged"=>"database_incompatible_or_damaged",
            "database_schema_incompatible"=>"database_schema_incompatible",
            "database_not_front"=>"database_not_front",
            "database_damaged"=>"database_damaged",
            "database_locked"=>"database_locked",
            "database_access_denied"=>"database_access_denied",
            "database_unreadable"=>"database_unreadable",
            "database_foreign_key_issues"=>"database_foreign_key_issues",
            "database_check_failed"=>"database_check_failed",
            "upgrade_backup_incomplete"=>"upgrade_backup_incomplete",
            _=>"sidecar_initialization_failed",
        }));
    }
    let ready:Ready=serde_json::from_value(value).map_err(|_|"sidecar_initialization_failed")?;
    if ready.pid!=child_pid || ready.port==0 || !(32..=128).contains(&ready.token.len())
        || !ready.token.bytes().all(|c|c.is_ascii_alphanumeric() || c==b'-' || c==b'_') {return Err("sidecar_initialization_failed");}
    Ok(StartupMessage::Ready(ready))
}

// Closing our Job Object kills only descendants assigned by this shell, including on shell crash.
#[cfg(windows)]
struct OwnedJob(isize);
#[cfg(windows)]
impl OwnedJob {
    fn assign(child: &Child) -> std::io::Result<Self> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::{Foundation::CloseHandle, System::JobObjects::*};
        unsafe {
            let handle=CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if handle.is_null() {return Err(std::io::Error::last_os_error());}
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION=std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(handle,JobObjectExtendedLimitInformation,&info as *const _ as *const _,std::mem::size_of_val(&info) as u32)==0 || AssignProcessToJobObject(handle,child.as_raw_handle())==0 {
                CloseHandle(handle);return Err(std::io::Error::last_os_error());
            }
            Ok(Self(handle as isize))
        }
    }
}
#[cfg(windows)]
impl Drop for OwnedJob {fn drop(&mut self){unsafe{windows_sys::Win32::Foundation::CloseHandle(self.0 as _);}}}

struct Service { child: Child, ready: Ready, #[cfg(windows)] _job: OwnedJob }
impl Service {
    fn stop(&mut self) {
        if matches!(self.child.try_wait(),Ok(Some(_))){return;}
        if let Ok(mut stream)=TcpStream::connect_timeout(&format!("127.0.0.1:{}",self.ready.port).parse().unwrap(),Duration::from_secs(1)) {
            let _=stream.set_write_timeout(Some(Duration::from_secs(1)));
            let request=format!("POST /_desktop/shutdown HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",self.ready.port,self.ready.token);
            let _=stream.write_all(request.as_bytes());
        }
        let start=Instant::now();
        while start.elapsed()<Duration::from_secs(8) {
            if matches!(self.child.try_wait(),Ok(Some(_))){return;}
            std::thread::sleep(Duration::from_millis(50));
        }
        let _=self.child.kill();let _=self.child.wait();
    }
}
impl Drop for Service {fn drop(&mut self){self.stop();}}

fn data_dir(app: &tauri::App) -> Result<PathBuf,Box<dyn std::error::Error>> {
    let exe=std::env::current_exe()?;
    let parent=exe.parent().ok_or("Program directory unavailable")?;
    let folder=if let Some(value)=std::env::var_os("FRONT_DATA_DIR") {PathBuf::from(value)}
        else if parent.join("Front.portable").is_file(){parent.join("FrontData")}
        else{app.path().app_local_data_dir()?};
    fs::create_dir_all(&folder).map_err(|_|"data_directory_unwritable")?;
    // Check before WebView writes its cache. A collision never overwrites a file.
    let probe=folder.join(format!(".front-shell-check-{}-{}",std::process::id(),SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos()));
    let mut created=false;
    let access=(||->std::io::Result<()>{
        let mut file=fs::OpenOptions::new().write(true).create_new(true).open(&probe)?;created=true;
        file.write_all(b"Front")?;file.sync_all()?;Ok(())
    })();
    let cleaned=if created{fs::remove_file(&probe)}else{Ok(())};
    if access.is_err() || cleaned.is_err(){return Err("data_directory_unwritable".into());}
    Ok(folder)
}

fn start_service(binary: &Path, folder: &Path, cancelled:&AtomicBool, progress:impl Fn(&'static str,Option<u64>,Option<u64>)) -> Result<Service,Box<dyn std::error::Error>> {
    if cancelled.load(Ordering::SeqCst){return Err("startup_cancelled".into());}
    let mut command=Command::new(binary);
    command.arg("--data-dir").arg(folder).arg("--startup-events").stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null());
    #[cfg(windows)] command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    let mut child=command.spawn()?;
    #[cfg(windows)] let job=match OwnedJob::assign(&child){Ok(v)=>v,Err(e)=>{let _=child.kill();let _=child.wait();return Err(e.into());}};
    let stdout=child.stdout.take().ok_or("No sidecar pipe")?;
    let (tx,rx)=mpsc::sync_channel(8);
    std::thread::spawn(move || {
        use std::io::Read;
        let mut reader=BufReader::new(stdout);
        loop {
            let mut line=String::new();
            match std::io::Read::by_ref(&mut reader).take(4097).read_line(&mut line) {
                Ok(0)|Err(_)=>break,
                Ok(_)=>{
                    let continuing=line.len()<=4096 && serde_json::from_str::<serde_json::Value>(&line).ok().is_some_and(|v|v.get("phase").is_some());
                    if tx.send(line).is_err() || !continuing{break;}
                }
            }
        }
        let _=std::io::copy(&mut reader,&mut std::io::sink());
    });
    let result=(||{
        let start=Instant::now();let mut extended=false;
        loop {
            if cancelled.load(Ordering::SeqCst){return Err("startup_cancelled".into());}
            if start.elapsed()>Duration::from_secs(if extended{1800}else{120}){return Err("startup_timeout".into());}
            match rx.recv_timeout(Duration::from_millis(250)) {
                Ok(line)=>match startup_message(&line,child.id()).map_err(std::io::Error::other)? {
                    StartupMessage::Progress(message,done,total,migration)=>{extended|=migration;progress(message,done,total);},
                    StartupMessage::Ready(ready)=>return Ok(ready),
                    StartupMessage::Error(code)=>return Err(std::io::Error::other(code).into()),
                },
                Err(mpsc::RecvTimeoutError::Timeout)=>{if child.try_wait()?.is_some(){return Err("sidecar_initialization_failed".into());}},
                Err(mpsc::RecvTimeoutError::Disconnected)=>return Err("sidecar_initialization_failed".into()),
            }
        }
    })();
    match result {
        Ok(ready)=>Ok(Service{child,ready,#[cfg(windows)] _job:job}),
        Err(e)=>{let _=child.kill();let _=child.wait();Err(e)}
    }
}

fn main() {
    let started=Instant::now();
    let result=tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![updates::desktop_update])
    .setup(move|app| {
        if let Some(key)=option_env!("FRONT_UPDATE_PUBLIC_KEY").filter(|v|!v.trim().is_empty()) {
            app.handle().plugin(tauri_plugin_updater::Builder::new().pubkey(key).build())?;
        }
        let folder=data_dir(app)?;
        let binary=app.path().resource_dir()?.join("backend/front-backend.exe");
        let cancelled=Arc::new(AtomicBool::new(false));
        app.manage(StartupLifecycle(cancelled.clone()));
        app.manage(Mutex::new(None::<Service>));
        let view=Arc::new(Mutex::new(StartupView{message:"正在检查本机资料…",done:None,total:None,failed:false}));
        let origin=Arc::new(Mutex::new(None::<String>));
        let timings=Arc::new(Mutex::new(StartupTimings{process_id:std::process::id(),..Default::default()}));
        let navigation_origin=origin.clone();let loaded_origin=origin.clone();let loaded_view=view.clone();
        let loaded_timings=timings.clone();let timing_folder=folder.clone();
        // One WebView is reused for the splash and the shared Vue application.
        let window=WebviewWindowBuilder::new(app,"main",WebviewUrl::App("index.html".into()))
            .title("Front Preview").inner_size(1280.0,850.0).min_inner_size(720.0,540.0)
            .data_directory(folder.join("webview"))
            .on_navigation(move|url|{
                let allowed=navigation_origin.lock().unwrap();
                allowed.as_ref().map_or_else(||local_splash(url),|o|url.origin().ascii_serialization()==*o)
            })
            .on_page_load(move|window,payload|{
                if matches!(payload.event(),tauri::webview::PageLoadEvent::Finished) && local_splash(payload.url()) {
                    render_startup(&window,&loaded_view);
                }
                if matches!(payload.event(),tauri::webview::PageLoadEvent::Finished) && payload.url().path()=="/"
                    &&loaded_origin.lock().unwrap().as_ref().is_some_and(|o|payload.url().origin().ascii_serialization()==*o){
                    record_startup(&timing_folder,&loaded_timings,"document",started);
                }
            })
            .build()?;
        {
            let mut value=timings.lock().unwrap();value.display_scale_factor=window.scale_factor().ok();
            if let Ok(size)=window.inner_size(){value.initial_inner_width=Some(size.width);value.initial_inner_height=Some(size.height);}
        }
        record_startup(&folder,&timings,"window",started);
        let handle=app.handle().clone();
        std::thread::spawn(move||{
            let result:Result<(),Box<dyn std::error::Error>>=(||{
                let service=start_service(&binary,&folder,&cancelled,|message,done,total|{
                    *view.lock().unwrap()=StartupView{message,done,total,failed:false};
                    render_startup(&window,&view);
                })?;
                record_startup(&folder,&timings,"service",started);
                let port=service.ready.port;
                let url=format!("http://127.0.0.1:{}/_desktop/bootstrap#{}",port,service.ready.token);
                let allowed_origin=format!("http://127.0.0.1:{}",port);
                handle.manage(updates::Updates::new(folder.clone(),allowed_origin.clone(),handle.package_info().version.to_string())?);
                handle.add_capability(tauri::ipc::CapabilityBuilder::new("front-updates")
                    .local(false).window("main").remote(format!("{allowed_origin}/*"))
                    .permission("allow-desktop-update"))?;
                {
                    let state=handle.state::<Mutex<Option<Service>>>();let mut slot=state.lock().unwrap();
                    if cancelled.load(Ordering::SeqCst){return Err("startup_cancelled".into());}
                    *slot=Some(service);
                }
                *origin.lock().unwrap()=Some(allowed_origin);
                if !cancelled.load(Ordering::SeqCst){window.navigate(url.parse()?)?;}
                Ok(())
            })();
            if let Err(error)=result {
                let state=handle.state::<Mutex<Option<Service>>>();
                if let Some(mut service)=state.lock().unwrap().take(){service.stop();}
                if !cancelled.load(Ordering::SeqCst){
                    *view.lock().unwrap()=StartupView{message:startup_error_text(&error.to_string()),done:None,total:None,failed:true};
                    render_startup(&window,&view);
                }
            }
        });
        Ok(())
    }).build(tauri::generate_context!());
    let app=match result {Ok(app)=>app,Err(error)=>{startup_error(&error.to_string());return;}};
    app.run(|app,event| {
        if matches!(event,tauri::RunEvent::ExitRequested{..} | tauri::RunEvent::Exit) {
            if let Some(state)=app.try_state::<StartupLifecycle>(){state.0.store(true,Ordering::SeqCst);}
            if let Some(state)=app.try_state::<Mutex<Option<Service>>>() {
                if let Ok(mut guard)=state.lock(){if let Some(mut service)=guard.take(){service.stop();}}
            }
        }
    });
}

fn startup_error_text(code:&str)->&'static str {
    match code {
        "database_schema_incompatible"=>return "当前 Front 不支持此资料库结构，存在未知或无法安全迁移的表或字段；这不代表数据库损坏。未执行升级，请核对版本，或在独立目录验证备份，不要重置资料库。",
        "database_not_front"=>return "所选文件是 SQLite 数据库，但缺少 Front 核心数据表。请核对资料目录，或在独立目录验证备份；不会自动重新建库或覆盖。",
        "database_damaged"=>return "SQLite 检查发现数据库格式或完整性异常。已停止升级，请保留原数据库及 WAL 文件，并在独立目录诊断备份；不要重置或覆盖原件。",
        "database_locked"=>return "SQLite 资料库被其他进程锁定。请检查是否有 Web、桌面版或备份工具正在使用同一目录，关闭相关实例后重试；未执行修复。",
        "database_access_denied"=>return "Front 没有读取或访问数据库的权限。请检查数据库文件及目录权限；这不代表资料库损坏，原件未被替换。",
        "database_unreadable"=>return "Front 无法读取数据库文件。请检查路径、磁盘、权限及 WAL 所在目录；尚不能判断资料库是否损坏，未执行修复。",
        "database_foreign_key_issues"=>return "资料库完整性检查通过，但存在关联记录异常。已停止升级，请先在独立副本检查外键报告；不会自动删除或修复原记录。",
        "database_check_failed"=>return "资料库检查未能完成，尚不能判断是否损坏。请核对程序版本并查看资料目录日志，在独立副本诊断；不会自动重置。",
        _=>{}
    }
    if code.contains("data_directory_in_use") {"Front 资料目录正在使用中。请先关闭使用该目录的 Front 窗口。"}
        else if code.contains("data_directory_unwritable") {"Front 无法写入资料目录。请检查磁盘空间和文件夹权限；便携版可移到可写目录，或通过 FRONT_DATA_DIR 指定独立目录。原有资料未被覆盖。"}
        else if code.contains("database_incompatible_or_damaged") {"Front 检测到不兼容或损坏的资料库，已停止升级。请使用较新版本或在独立目录验证备份。"}
        else if code.contains("upgrade_backup_incomplete") {"Front 升级前完整备份未通过验证，已保留原资料。请先检查缺失的托管素材和备份报告。"}
        else if code.contains("startup_timeout") {"Front 初始化等待超时，已停止本实例服务。原资料和已生成的备份保留，请检查磁盘及资料目录日志后重试。"}
        else {"Front 无法启动。请确认已完整解压程序、WebView2 已安装，资料目录可写。便携版请移到可写目录重试。详情见资料目录 logs/desktop.log。"}
}
fn startup_error(code:&str) {
    let text=startup_error_text(code);
    #[cfg(windows)] unsafe {
        use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW,MB_OK,MB_ICONERROR};
        let message:Vec<u16>=text.encode_utf16().chain(Some(0)).collect();
        let title:Vec<u16>="Front Preview".encode_utf16().chain(Some(0)).collect();
        MessageBoxW(std::ptr::null_mut(),message.as_ptr(),title.as_ptr(),MB_OK|MB_ICONERROR);
    }
    #[cfg(not(windows))] eprintln!("{text}");
}

#[cfg(test)]
mod startup_tests {
    use super::*;
    #[test]
    fn startup_tests_bound_messages_and_never_display_raw_phase_or_error() {
        assert!(matches!(startup_message(r#"{"phase":"backup","done":3,"total":10}"#,42),Ok(StartupMessage::Progress(_,Some(3),Some(10),true))));
        assert!(startup_message(r#"{"phase":"arbitrary private filename"}"#,42).is_err());
        assert!(startup_message(&"X".repeat(4097),42).is_err());
        assert!(matches!(startup_message(r#"{"error":"arbitrary private path"}"#,42),Ok(StartupMessage::Error("sidecar_initialization_failed"))));
        assert!(matches!(startup_message(r#"{"phase":"backup","done":99,"total":10}"#,42),Ok(StartupMessage::Progress(_,None,Some(10),true))));
        for code in ["database_schema_incompatible","database_not_front","database_damaged","database_locked","database_access_denied","database_unreadable","database_foreign_key_issues","database_check_failed"] {
            let line=serde_json::json!({"error":code}).to_string();
            assert!(matches!(startup_message(&line,42),Ok(StartupMessage::Error(found)) if found==code));
            assert_ne!(startup_error_text(code),startup_error_text("unknown"));
        }
        assert_ne!(startup_error_text("database_schema_incompatible"),startup_error_text("database_damaged"));
    }
    #[test]
    fn startup_tests_validate_owned_pid_token_and_navigation_origin() {
        let valid=serde_json::json!({"port":23456,"pid":42,"token":"generated_test_token_with_32_characters"}).to_string();
        assert!(matches!(startup_message(&valid,42),Ok(StartupMessage::Ready(_))));
        assert!(startup_message(&valid,43).is_err());
        assert!(startup_message(r#"{"port":123,"pid":42,"token":"short"}"#,42).is_err());
        assert!(local_splash(&"http://tauri.localhost/index.html".parse().unwrap()));
        assert!(local_splash(&"tauri://localhost/index.html".parse().unwrap()));
        assert!(!local_splash(&"http://tauri.localhost.evil.example/".parse().unwrap()));
        assert!(!local_splash(&"http://127.0.0.1:8000/".parse().unwrap()));
    }
}
