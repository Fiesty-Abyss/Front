#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{fs, io::{BufRead, BufReader, Write}, net::TcpStream, path::{Path, PathBuf}, process::{Child, Command, Stdio}, sync::{mpsc, Mutex}, time::{Duration, Instant}};
use serde::Deserialize;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[derive(Deserialize)]
struct Ready { port: u16, token: String, pid: u32 }

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
    Ok(folder)
}

fn start_service(binary: &Path, folder: &Path) -> Result<Service,Box<dyn std::error::Error>> {
    let mut command=Command::new(binary);
    command.arg("--data-dir").arg(folder).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null());
    #[cfg(windows)] command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    let mut child=command.spawn()?;
    #[cfg(windows)] let job=match OwnedJob::assign(&child){Ok(v)=>v,Err(e)=>{let _=child.kill();let _=child.wait();return Err(e.into());}};
    let stdout=child.stdout.take().ok_or("No sidecar pipe")?;
    let (tx,rx)=mpsc::channel();
    std::thread::spawn(move || {
        let mut line=String::new();
        // Limit startup handshake to prevent unbounded output memory.
        use std::io::Read;
        let mut reader=BufReader::new(stdout);
        let _=std::io::Read::by_ref(&mut reader).take(4096).read_line(&mut line);
        let _=tx.send(line);
        let _=std::io::copy(&mut reader,&mut std::io::sink());
    });
    let result=(||{
        let line=rx.recv_timeout(Duration::from_secs(120))?;
        let value:serde_json::Value=serde_json::from_str(&line)?;
        if let Some(code)=value.get("error").and_then(|v|v.as_str()) {
            return Err(std::io::Error::other(match code {
                "data_directory_in_use"=>"data_directory_in_use",
                "data_directory_unwritable"=>"data_directory_unwritable",
                "database_incompatible_or_damaged"=>"database_incompatible_or_damaged",
                "upgrade_backup_incomplete"=>"upgrade_backup_incomplete",
                _=>"sidecar_initialization_failed"
            }).into());
        }
        let ready: Ready=serde_json::from_value(value)?;
        if ready.pid!=child.id() || ready.port==0 || ready.token.len()<32 || !ready.token.bytes().all(|c|c.is_ascii_alphanumeric() || c==b'-' || c==b'_') {return Err("Invalid sidecar handshake".into());}
        Ok(ready)
    })();
    match result {
        Ok(ready)=>Ok(Service{child,ready,#[cfg(windows)] _job:job}),
        Err(e)=>{let _=child.kill();let _=child.wait();Err(e)}
    }
}

fn main() {
    let result=tauri::Builder::default().setup(|app| {
        let folder=data_dir(app)?;
        let binary=app.path().resource_dir()?.join("backend/front-backend.exe");
        let service=start_service(&binary,&folder)?;
        let port=service.ready.port;
        let url=format!("http://127.0.0.1:{}/_desktop/bootstrap#{}",port,service.ready.token);
        app.manage(Mutex::new(Some(service)));
        let allowed_origin=format!("http://127.0.0.1:{}",port);
        WebviewWindowBuilder::new(app,"main",WebviewUrl::External(url.parse()?))
            .title("Front Preview").inner_size(1280.0,850.0).min_inner_size(720.0,540.0)
            .data_directory(folder.join("webview"))
            .on_navigation(move|url|url.origin().ascii_serialization()==allowed_origin)
            .build()?;
        Ok(())
    }).build(tauri::generate_context!());
    let app=match result {Ok(app)=>app,Err(error)=>{startup_error(&error.to_string());return;}};
    app.run(|app,event| {
        if matches!(event,tauri::RunEvent::ExitRequested{..} | tauri::RunEvent::Exit) {
            if let Some(state)=app.try_state::<Mutex<Option<Service>>>() {
                if let Ok(mut guard)=state.lock(){if let Some(mut service)=guard.take(){service.stop();}}
            }
        }
    });
}

fn startup_error(code:&str) {
    let text=if code.contains("data_directory_in_use") {"Front 资料目录正在使用中。请先关闭使用该目录的 Front 窗口。"}
        else if code.contains("data_directory_unwritable") {"Front 无法写入资料目录。请检查磁盘空间和文件夹权限；便携版可移到可写目录，或通过 FRONT_DATA_DIR 指定独立目录。原有资料未被覆盖。"}
        else if code.contains("database_incompatible_or_damaged") {"Front 检测到不兼容或损坏的资料库，已停止升级。请使用较新版本或在独立目录验证备份。"}
        else if code.contains("upgrade_backup_incomplete") {"Front 升级前完整备份未通过验证，已保留原资料。请先检查缺失的托管素材和备份报告。"}
        else {"Front 无法启动。请确认已完整解压程序、WebView2 已安装，资料目录可写。便携版请移到可写目录重试。详情见资料目录 logs/desktop.log。"};
    #[cfg(windows)] unsafe {
        use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW,MB_OK,MB_ICONERROR};
        let message:Vec<u16>=text.encode_utf16().chain(Some(0)).collect();
        let title:Vec<u16>="Front Preview".encode_utf16().chain(Some(0)).collect();
        MessageBoxW(std::ptr::null_mut(),message.as_ptr(),title.as_ptr(),MB_OK|MB_ICONERROR);
    }
    #[cfg(not(windows))] eprintln!("{text}");
}
