"""Extract every real video frame for a technical visual smoke review."""
import argparse,json,math,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

def main():
    p=argparse.ArgumentParser();p.add_argument("--snapshots",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--ffmpeg",required=True);args=p.parse_args()
    font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",14)
    for cid in ("flow-blink","flow-sequence","flow-parallel"):
        source=args.snapshots/cid;target=args.out/cid;target.mkdir(parents=True,exist_ok=True)
        subprocess.run([args.ffmpeg,"-v","error","-i",str(source/"preview.mp4"),"-vsync","0",str(target/"frame_%04d.png")],check=True)
        frames=sorted(target.glob("frame_*.png"));trajectory=[json.loads(x) for x in (source/"trajectory.jsonl").read_text(encoding="utf-8-sig").splitlines()]
        assert len(frames)==len(trajectory)
        for page in range(math.ceil(len(frames)/25)):
            selected=frames[page*25:(page+1)*25];cols=5;w=240;h=320
            sheet=Image.new("RGB",(cols*w,math.ceil(len(selected)/cols)*h),(236,236,236));draw=ImageDraw.Draw(sheet)
            for j,frame in enumerate(selected):
                i=page*25+j;im=Image.open(frame).convert("RGB");im.thumbnail((w,280));x=j%cols*w;y=j//cols*h;sheet.paste(im,(x+(w-im.width)//2,y))
                sample=trajectory[i];params={v["id"]:v["value"] for v in sample["parameters"]}
                draw.text((x+2,y+282),f'{cid} f{i} {sample["video_time_ms"]/1000:.3f}s',font=font,fill="black")
                draw.text((x+2,y+300),f'eye={params.get("ParamEyeLOpen",0):.2f} Y={params.get("ParamAngleY",0):.1f} arm={params.get("PARAM_Arm_RT_Angle",0):.1f}',font=font,fill="black")
            out=args.out/f"{cid}_page{page+1}.png";sheet.save(out);print(out.resolve())

if __name__=="__main__":main()
