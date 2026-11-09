//! A path suggestion, not a filesystem grant. No plugin dialog/FS permissions are exposed.
use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
use serde::Deserialize;

pub struct PathPicker { origin: String, busy: Arc<AtomicBool> }
impl PathPicker {
    pub fn new(origin: String) -> Self { Self { origin, busy: Arc::new(AtomicBool::new(false)) } }
    fn authorize(&self, label: &str, url: &tauri::Url) -> Result<(), String> {
        if label != "main" || url.origin().ascii_serialization() != self.origin
            || !url.username().is_empty() || url.password().is_some() {
            return Err("path_picker_forbidden".into());
        }
        Ok(())
    }
    fn acquire(&self) -> Result<Lease, String> {
        self.busy.compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .map_err(|_| "path_picker_busy".to_string())?;
        Ok(Lease(self.busy.clone()))
    }
}
struct Lease(Arc<AtomicBool>);
impl Drop for Lease { fn drop(&mut self) { self.0.store(false, Ordering::SeqCst); } }

#[derive(Clone, Copy, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Purpose { DiscoveryRoot, AssetFolder, ProjectFolder, AudioFolder, ModelsFolder, ModelFile, Live2dFolder, Live2dArchive }
impl Purpose {
    fn title(self) -> &'static str {
        match self {
            Self::DiscoveryRoot => "选择扫描根目录", Self::AssetFolder => "选择素材目录",
            Self::ProjectFolder => "选择项目目录", Self::AudioFolder => "选择音声目录",
            Self::ModelsFolder => "选择模型目录", Self::ModelFile => "选择模型文件",
            Self::Live2dFolder => "选择 Live2D 模型目录", Self::Live2dArchive => "选择 Live2D 模型压缩包",
        }
    }
    fn extensions(self) -> &'static [&'static str] {
        match self {
            Self::ModelFile => &["safetensors", "ckpt", "pt", "pth", "bin", "gguf"],
            Self::Live2dArchive => &["zip", "rar"], _ => &[],
        }
    }
}

#[tauri::command]
pub async fn desktop_pick_path(window: tauri::WebviewWindow, state: tauri::State<'_, PathPicker>, purpose: Purpose) -> Result<Option<String>, String> {
    state.authorize(window.label(), &window.url().map_err(|_| "path_picker_forbidden")?)?;
    #[cfg(not(windows))]
    { let _ = purpose; Err("path_picker_unsupported".into()) }
    #[cfg(windows)]
    {
        use tauri_plugin_dialog::DialogExt;
        let lease = state.acquire()?;
        let (send, receive) = tokio::sync::oneshot::channel();
        let mut dialog = window.dialog().file().set_parent(&window).set_title(purpose.title());
        let extensions = purpose.extensions();
        if !extensions.is_empty() { dialog = dialog.add_filter("支持的文件", extensions); }
        let finished = move |selected: Option<tauri_plugin_dialog::FilePath>| {
            // The callback owns this lease: abandoning the IPC future must not open a second modal.
            let result = selected.map(|file| {
                let path = file.into_path().map_err(|_| "path_picker_invalid".to_string())?;
                if !path.is_absolute() { return Err("path_picker_invalid".into()); }
                path.into_os_string().into_string().map_err(|_| "path_picker_invalid".into())
            }).transpose();
            drop(lease);
            let _ = send.send(result);
        };
        // Use the Rust API directly. The plugin's JS open command expands asset/FS scope.
        // This command deliberately does neither, and does not read or scan the selected path.
        if extensions.is_empty() { dialog.pick_folder(finished); } else { dialog.pick_file(finished); }
        receive.await.map_err(|_| "path_picker_closed".to_string())?
    }
}

#[cfg(test)]
mod path_picker_tests {
    use super::*;
    #[test]
    fn exact_origin_and_main_window_only() {
        let state = PathPicker::new("http://127.0.0.1:51234".into());
        assert!(state.authorize("main", &"http://127.0.0.1:51234/discovery".parse().unwrap()).is_ok());
        for (label, url) in [("other", "http://127.0.0.1:51234/"), ("main", "http://127.0.0.1:8000/"),
            ("main", "https://example.org/"), ("main", "http://localhost:51234/"),
            ("main", "http://user@127.0.0.1:51234/")] {
            assert!(state.authorize(label, &url.parse().unwrap()).is_err());
        }
    }
    #[test]
    fn one_dialog_lease_and_reusable_after_cancel() {
        let state = PathPicker::new(String::new());
        let lease = state.acquire().unwrap();
        assert!(state.acquire().is_err());
        drop(lease);
        let next = state.acquire().unwrap();
        assert!(state.acquire().is_err());
        drop(next);
        assert!(state.acquire().is_ok());
    }
    #[test]
    fn purposes_are_closed_and_file_filters_are_explicit() {
        assert!(serde_json::from_str::<Purpose>("\"shell\"").is_err());
        assert!(serde_json::from_str::<Purpose>("\"discovery_root\"").unwrap().extensions().is_empty());
        assert_eq!(Purpose::Live2dArchive.extensions(), &["zip", "rar"]);
        assert!(!Purpose::ModelFile.extensions().contains(&"exe"));
        assert!(!Purpose::AudioFolder.title().is_empty());
    }
}
