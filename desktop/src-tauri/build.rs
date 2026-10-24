fn main() {
    println!("cargo:rerun-if-env-changed=FRONT_UPDATE_PUBLIC_KEY");
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["desktop_update"])
    )).expect("desktop build configuration");
}
