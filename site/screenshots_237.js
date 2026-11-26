// usage: node shot.js <publicdir> <outdir> <pages comma> [full]
const puppeteer=require('puppeteer');const fs=require('fs');const path=require('path');
(async()=>{
 const [,,dir,out,pages,full]=process.argv; fs.mkdirSync(out,{recursive:true});
 const b=await puppeteer.launch({headless:'new',executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
 const errs=[];
 for(const pg of pages.split(',')){
  for(const [w,h,tag] of [[1280,900,'1280'],[390,844,'390']]){
   for(const th of ['light','dark']){
    const p=await b.newPage(); await p.setViewport({width:w,height:h});
    await p.emulateMediaFeatures([{name:'prefers-color-scheme',value:th}]);
    p.on('pageerror',e=>errs.push(pg+' '+e.message));
    await p.goto('file://'+path.resolve(dir,pg+'.html'),{waitUntil:'load'});
    const sw=await p.evaluate(()=>document.documentElement.scrollWidth);
    if(sw>w+1) errs.push(`${pg} ${tag} ${th}: horizontal overflow ${sw}>${w}`);
    await p.screenshot({path:path.join(out,`${pg.replace('/','_')}_${tag}_${th}.png`),fullPage:full==='full'});
    await p.close();
   }}}
 await b.close(); console.log(errs.join('\n')||'no errors');
})();
