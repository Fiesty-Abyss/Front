export const editionLabels = {record_type:'记录类型',isbn_10:'ISBN-10',isbn_13:'ISBN-13',languages:'语言代码',work_ids:'所属作品 ID',edition_name:'版次说明',publish_date:'出版日期（来源原文）'}
export function bookRecordKind(item) {
  if (item?.kind && item.kind !== 'book') return null
  if (item?.provider !== 'openlibrary' && item?.source !== 'openlibrary') return null
  if (item.record_type === 'edition' && /^OL\d{1,18}M$/.test(item.sid)) return '具体版次'
  if (/^OL\d{1,18}W$/.test(item.sid)) return '作品条目（非具体版次）'
  return '来源记录（版次身份未确认）'
}
export function metadataSearchBody({kind,title,author,year,providers}) {
  let date = null
  if (kind === 'book' && year !== '' && year != null) {
    date = Number(year)
    if (!Number.isInteger(date) || date<1 || date>9999) throw new Error('出版年份应为1–9999的整数，也可留空。')
  }
  return {online:true,kind,title,author:kind==='book'?(author?.trim()||null):null,year:date,providers:[...providers]}
}
