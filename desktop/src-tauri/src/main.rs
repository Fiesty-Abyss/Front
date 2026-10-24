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
    fs::create_dir_all(&folder).map_err(|_|"Front data directory is not writable. Move portable Front to a writable folder or set FRONT_DATA_DIR.")?;
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
        let _=BufReader::new(stdout).take(4096).read_line(&mut line);
        let _=tx.send(line);
    });
    let result=(||{
        let line=rx.recv_timeout(Duration::from_secs(120))?;
        let ready: Ready=serde_json::from_str(&line).map_err(|_|"Front backend could not initialize. Check data permissions, database compatibility and whether the directory is in use.")?;
        if ready.pid!=child.id() || ready.port==0 || ready.token.len()<32 || !ready.token.bytes().all(|c|c.is_ascii_alphanumeric() || c==b'-' || c==b'_') {return Err("Invalid sidecar handshake".into());}
        Ok(ready)
    })();
    match result {
        Ok(ready)=>Ok(Service{child,ready,#[cfg(windows)] _job:job}),
        Err(e)=>{let _=child.kill();let _=child.wait();Err(e)}
    }
}

fn main() {
    let app=tauri::Builder::default().setup(|app| {
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
    }).build(tauri::generate_context!()).expect("Front failed to start. See the data directory lifecycle log.");
    app.run(|app,event| {
        if matches!(event,tauri::RunEvent::ExitRequested{..} | tauri::RunEvent::Exit) {
            if let Some(state)=app.try_state::<Mutex<Option<Service>>>() {
                if let Ok(mut guard)=state.lock(){if let Some(mut service)=guard.take(){service.stop();}}
            }
        }
    });
}
