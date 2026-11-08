// Detached form snapshots: a page refresh must not rebase an unsaved draft's version.
export function draftFromSegment(row) {
  return {text:row.text,speaker:row.speaker,profile_id:row.profile_id,language:row.recipe.language||'',speed:row.recipe.speed||1,confirm_speaker:row.source?.speaker_confirmed||false}
}
export function emptyVoiceDraft() {
  return {text:'',speaker:'旁白',profile_id:null,language:'',speed:1,confirm_speaker:false}
}
function signature(value) {
  if (!value) return null
  return JSON.stringify([value.text??'',value.speaker??'',value.profile_id===''?null:value.profile_id??null,
    value.language??'',value.speed??1,Boolean(value.confirm_speaker)])
}
export function draftChanged(draft,saved) { return Boolean(draft)&&signature(draft)!==signature(saved) }
export function exportContext(project,segments=[]) {
  return JSON.stringify([project?.uid??null,project?.version??null,segments.map(row=>row.uid)])
}
