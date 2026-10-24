"""Lazy, bounded raster processing. No inference service or drawing engine."""
import hashlib

MAX_PIXELS=32_000_000
MAX_SOURCE=128*1024*1024


def process(source,destination,*,operation,format='png',background='white',expected_sha=None,check=lambda:None):
    from PIL import Image,ImageOps,ImageFilter,ImageDraw
    before=source.stat()
    if before.st_size>MAX_SOURCE:raise ValueError('处理源文件超过128MiB；请先使用外部编辑器缩小副本')
    with Image.open(source) as probe:
        if probe.width*probe.height>MAX_PIXELS:raise ValueError('处理图像超过3200万像素；请先缩小副本')
    h=hashlib.sha256()
    with source.open('rb') as stream:
        while block:=stream.read(1024*1024):check();h.update(block)
    if expected_sha and h.hexdigest()!=expected_sha:raise ValueError('原图Hash变化，停止处理以保护版本来源')
    check()
    with Image.open(source) as original:
        image=ImageOps.exif_transpose(original).convert('RGBA')
    after=source.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('处理期间原图变化，请重新确认版本')
    check()
    white=Image.new('RGBA',image.size,'white');white.alpha_composite(image)
    size=image.size
    if operation=='lineart':
        image.close()
        gray=ImageOps.grayscale(white);white.close();edge=gray.filter(ImageFilter.FIND_EDGES);gray.close()
        line=ImageOps.invert(ImageOps.autocontrast(edge))
        edge.close()
        # FIND_EDGES leaves a source-colour border; discard that algorithm artifact.
        ImageDraw.Draw(line).rectangle((0,0,line.width-1,line.height-1),outline=255,width=1)
        if background=='transparent':
            image=Image.new('RGBA',line.size,(0,0,0,0));image.putalpha(ImageOps.invert(line))
        else:image=line.convert('RGB')
        line.close()
        format='png'
    elif background=='white' or format=='jpeg':image.close();image=white.convert('RGB');white.close()
    else:white.close()
    check()
    image.save(destination,format={'png':'PNG','jpeg':'JPEG','webp':'WEBP'}[format],**({'quality':95} if format in ('jpeg','webp') else {}))
    image.close();check()
    return {'source_sha256':h.hexdigest(),'width':size[0],'height':size[1],'raster':True,'animated_notice':'只处理首帧；不进行背景移除、矢量化或语义识别'}
