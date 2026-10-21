/** Run only inside the documented local computer-use runtime with a selected tab.
 * No navigation, HTTP client, knowledge process/import, or database access.
 */
import {mkdir,writeFile,access} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {join,resolve,dirname} from 'node:path';

export async function captureBrowserExport({tab,source,selector,outputDir}) {
  if(source?.acquisition?.kind!=='approved_local_file'||source?.policy?.allow_import!==true||source?.policy?.uses?.local_cache?.status!=='allowed')
    throw Error('An explicit permitted source plan is required before DOM access; this adapter grants no rights.');
  if(!/^[a-z0-9][a-z0-9-]{0,79}$/.test(source.source_id)||typeof selector!=='string'||!selector||selector.length>500)
    throw Error('Bounded source ID and explicit article selector required.');
  const root=resolve(outputDir);
  for(let parent=root;;parent=dirname(parent)){
    for(const name of ['.git','knowledge.sqlite3']){
      let exists=false;try{await access(join(parent,name));exists=true}catch{}
      if(exists)throw Error('Capture output must be outside Git checkouts and knowledge archive directories.');
    }
    if(parent===dirname(parent))break;
  }
  if(await tab.url()!==source.original_url)throw Error('Selected tab URL differs; do not follow redirects or switch tabs automatically.');
  const result=await tab.playwright.evaluate(({selector})=>{
    const nodes=document.querySelectorAll(selector);
    if(nodes.length!==1)throw Error('The article selector must match exactly one element.');
    const article=nodes[0],license=document.getElementById('footer-info-copyright');
    return {final_url:location.href,title:document.title,html:article.outerHTML,
      page_updated:document.getElementById('footer-info-lastmod')?.textContent||null,
      license_statement:license?.textContent||null,
      license_links:license?[...license.querySelectorAll('a')].map(a=>({href:a.href,text:a.textContent})):[]};
  },{selector});
  if(result.final_url!==source.original_url)throw Error('Page changed during capture.');
  const raw=Buffer.from(result.html,'utf8');
  if(raw.length<40||raw.length>2000000)throw Error('Rendered article outside the 40-byte to 2-MB bound.');
  const receipt={format:'ssr.browser-export.v1',requested_url:source.original_url,final_url:result.final_url,
    title:result.title,captured_at:new Date().toISOString(),raw_sha256:createHash('sha256').update(raw).digest('hex'),
    export_format:'rendered_dom_html',selector,scope:'Selected rendered article DOM; not network response bytes or account/navigation context',
    page_updated:result.page_updated,license_statement:result.license_statement,license_links:result.license_links,
    method:'local_chrome_computer_use',http_status:null};
  await mkdir(root,{recursive:true});
  const file=join(root,source.source_id+'.html'),receiptFile=join(root,source.source_id+'.browser.json');
  await writeFile(file,raw,{flag:'wx'});await writeFile(receiptFile,JSON.stringify(receipt,null,2),{flag:'wx'});
  return {file,receiptFile,raw_bytes:raw.length,raw_sha256:receipt.raw_sha256,knowledge_database_touched:false};
}
