"""Optional brand asset rebuild: pip install fonttools pillow cairosvg."""
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from PIL import Image,ImageDraw,ImageFont
import cairosvg
import os
os.chdir(Path(__file__).resolve().parent.parent)
font=TTFont('static/font-7.woff2');glyphs=font.getGlyphSet();cmap=font.getBestCmap();scale=43/font['head'].unitsPerEm;x=86;paths=[]
for char in 'reachmark':
    name=cmap[ord(char)];pen=SVGPathPen(glyphs);glyphs[name].draw(TransformPen(pen,(scale,0,0,-scale,x,55)));paths.append(pen.getCommands());x+=glyphs[name].width*scale-1.4
width=round(x+20);mark=Path('static/icon.svg').read_text();mark=mark[mark.index('<rect'):mark.index('</svg>')]
for mode,color in [('primary','#20251f'),('inverse','#f5f5ef')]:
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 80" role="img" aria-labelledby="title"><title id="title">Reachmark logo</title><g transform="translate(4 8)">{mark}</g><g fill="{color}">'+''.join('<path d="'+p+'"/>' for p in paths)+f'</g><circle cx="{x+4:.2f}" cy="52" r="3.4" fill="#a8c944"/></svg>'
    Path(f'static/logo-{mode}.svg').write_text(svg);Path(f'brand/reachmark-logo-{mode}.svg').write_text(svg)
    cairosvg.svg2png(bytestring=svg.encode(),write_to=f'brand/reachmark-logo-{mode}.png',output_width=width*3,output_height=240)
for size in [192,512]:cairosvg.svg2png(url='static/icon.svg',write_to=f'static/icon-{size}.png',output_width=size,output_height=size)
cairosvg.svg2png(url='static/icon.svg',write_to='brand/reachmark-symbol.png',output_width=1024,output_height=1024)
Path('brand/reachmark-symbol.svg').write_text(Path('static/icon.svg').read_text())
im=Image.new('RGB',(1200,630),'#20251f');d=ImageDraw.Draw(im);d.ellipse((770,-190,1400,440),outline='#39482b',width=1);d.ellipse((730,-230,1440,480),outline='#303b26',width=1)
logo=Image.open('brand/reachmark-logo-inverse.png').convert('RGBA');logo.thumbnail((350,95));im.paste(logo,(65,50),logo)
fp='static/font-7.woff2';regular='static/font-0.woff2'
d.text((70,237),'Find potential.',font=ImageFont.truetype(fp,78),fill='#f5f5ef');d.text((70,331),'Make your mark.',font=ImageFont.truetype(fp,78),fill='#d5f268')
d.text((73,520),'GLOBAL DISCOVERY   /   REAL WEBSITE SIGNALS   /   THOUGHTFUL OUTREACH',font=ImageFont.truetype(regular,17),fill='#8d9b7d');im.save('static/social-card.png')
