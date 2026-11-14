import json,sys,glob
d=sys.argv[1]
tot=ok=empty=err=0; vers=set(); read=0; readempty=0
for f in sorted(glob.glob(d+"/claude_code/*.jsonl")):
    names={}
    for ln in open(f):
        try: e=json.loads(ln)
        except: continue
        if e.get("type")=="system" and e.get("subtype")=="init": vers.add(e.get("claude_code_version"))
        m=e.get("message") or {}
        c=m.get("content")
        if not isinstance(c,list): continue
        for b in c:
            if b.get("type")=="tool_use": names[b["id"]]=b["name"]
            if b.get("type")=="tool_result":
                tot+=1
                cc=b.get("content")
                txt=cc if isinstance(cc,str) else "".join(x.get("text","") for x in cc or [] if isinstance(x,dict))
                if b.get("is_error"): err+=1; continue
                if txt.strip(): ok+=1
                else: empty+=1
                if names.get(b.get("tool_use_id"),"").endswith("read_file"):
                    read+=1; readempty+= (not txt.strip())
print(dict(versions=vers,total=tot,ok_with_text=ok,empty=empty,errors=err,read_file=read,read_file_empty=readempty))
