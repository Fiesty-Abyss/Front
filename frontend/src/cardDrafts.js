export function designState(raw) {
  try {
    const extensions=JSON.parse(raw||'{}')
    if(!extensions||Array.isArray(extensions)||typeof extensions!=='object')return {value:{schema:1},blocked:true}
    const value=extensions.front_design_v1
    if(value===undefined)return {value:{schema:1},blocked:false}
    if(!value||Array.isArray(value)||value.schema!==1)return {value:{schema:1},blocked:true}
    if(value.aliases!==undefined&&(!Array.isArray(value.aliases)||value.aliases.some(a=>typeof a!=='string')))return {value:{schema:1},blocked:true}
    for(const field of ['appearance','clothing','hair','eyes','notes'])if(value[field]!==undefined&&typeof value[field]!=='string')return {value:{schema:1},blocked:true}
    if(value.favorite!==undefined&&typeof value.favorite!=='boolean')return {value:{schema:1},blocked:true}
    for(const [key,max] of [['stars',5],['preference',100]])if(value[key]!==undefined&&(!Number.isInteger(value[key])||value[key]<0||value[key]>max))return {value:{schema:1},blocked:true}
    return {value,blocked:false}
  }catch{return {value:{schema:1},blocked:true}}
}

export function aliasExtensions(raw, input) {
  const extensions=JSON.parse(raw||'{}')
  if(!extensions||Array.isArray(extensions)||typeof extensions!=='object')throw new Error('扩展必须是JSON对象')
  const state=designState(raw)
  if(state.blocked)return extensions
  if(extensions.front_design_v1!==undefined||input.trim()){
    extensions.front_design_v1={...state.value,aliases:input.split(/[,，、]/).map(s=>s.trim()).filter(Boolean)}
  }
  return extensions
}
