(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CollectorLabUI = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function createFlow({request, render = () => {}, makeId = () => globalThis.crypto.randomUUID()}) {
    const state = {connected:false, busy:false, editing:true, requiresRefresh:false, server:null, result:null, message:'未連線；尚未執行。', error:false};
    const emit = () => render(state);
    function failed(error, mutation) {
      state.result = null; state.error = true;
      if (mutation && !error.knownRejected) {
        state.requiresRefresh = true;
        state.message = '連線中斷或輸出無法辨識；結果可能已保存。請先重新讀取，不要盲目重送。';
      } else state.message = error.message || '讀取失敗';
    }
    async function refresh() {
      if (state.busy) return false;
      state.busy=true; emit();
      try { const value=await request('/api/state');
        if (value.mode!=='collector_only') throw Error('這不是 collector 獨立模式；操作未啟用。');
        if(state.server&&state.server.session_id!==value.session_id){state.result=null;state.editing=true;}
        state.server=value; state.connected=true; state.requiresRefresh=false; state.error=false;
        state.message='已讀取合成 stage；HTTP／瀏覽器驗收狀態仍以證據為準。';
      } catch(error) { state.connected=false; failed(error,false); }
      finally { state.busy=false; emit(); }
      return state.connected;
    }
    async function submit(text, format, synthetic) {
      if (state.busy || !state.connected || state.requiresRefresh) return false;
      if (!synthetic) { state.error=true; state.message='請先確認只輸入合成資料。'; emit(); return false; }
      state.busy=true; state.result=null; state.editing=false; state.error=false; state.message='正在執行本機 intake 與 bundle…'; emit();
      try {
        const result=await request('/api/collector/intake', {request_id:makeId(), session_id:state.server.session_id, text, format, synthetic:true}, state.server.csrf_token);
        state.result=result; state.server.stage=result.readback;
        if(result.operations)state.server.operations=result.operations;
        if(result.artifacts)state.server.artifacts=result.artifacts;
        state.message=result.request_replayed?'同一請求已處理，回傳既有結果。':result.intake.state==='unchanged'?'相同內容已去重；本次觀測已保存。':'已保存合成 snapshot 與資料包。';
      } catch(error) { failed(error,true); }
      finally { state.busy=false; emit(); }
      return Boolean(state.result);
    }
    function clear() { if(state.busy)return false; state.result=null;state.editing=true;state.error=false;state.message=state.requiresRefresh?'輸入已清除；仍需重新讀取確認前次結果。':'輸入已清除，未送出請求。';emit();return true; }
    function back() { if(state.busy)return false;state.editing=true;state.message=state.requiresRefresh?'返回編輯；仍需重新讀取確認前次結果。':'返回編輯，未送出請求。';emit();return true; }
    async function newSession() {
      if(state.busy||!state.connected||state.requiresRefresh)return false;
      state.busy=true;emit();
      try { state.server=await request('/api/collector/new-session',{session_id:state.server.session_id},state.server.csrf_token);state.result=null;state.editing=true;state.error=false;state.message='已建立新的合成工作階段；舊資料與證據保留。'; }
      catch(error) { failed(error,true); }
      finally { state.busy=false;emit(); }
      return !state.error;
    }
    return {state,refresh,submit,clear,back,newSession};
  }
  function mount(doc, options={}) {
    const by=id=>doc.getElementById(id), make=(tag,text)=>{const e=doc.createElement(tag);e.textContent=text;return e;};
    const offline=(options.protocol || globalThis.location.protocol)==='file:';
    const fetchImpl=options.fetchImpl || globalThis.fetch.bind(globalThis);
    async function request(path, payload, token) {
      const config=payload?{method:'POST',headers:{'Content-Type':'application/json','X-Collector-Token':token},body:JSON.stringify(payload)}:{cache:'no-store'};
      const response=await fetchImpl(path,config);let value;
      try { value=await response.json(); } catch(error) { throw Error('回應不是有效 JSON；請重新讀取。'); }
      if(!response.ok){const error=Error(value.error || '操作失敗');error.knownRejected=response.status===400||response.status===403||response.status===404;throw error;}
      return value;
    }
    let lastCriteria=null;
    const flow=createFlow({request,render(state){
      by('labConnection').textContent=offline?'檔案預覽：未連線，操作未啟用。':state.connected?'已接上合成操作模式；真實網站與 knowledge 未接通。':'未連線；尚未執行。';
      by('labStatus').textContent=state.message;by('labStatus').className=state.error?'error':'small-note';
      for(const id of ['labSubmit','labNewSession'])by(id).disabled=state.busy||!state.connected||state.requiresRefresh||offline;
      for(const id of ['labText','labFormat','labConfirm','labExample','labClear','labBack'])by(id).disabled=state.busy;
      by('labReload').disabled=state.busy||offline;
      by('labForm').setAttribute('aria-busy',String(state.busy));
      const counts=state.server?.stage?.counts;
      by('labCounts').textContent=counts?'snapshot '+counts.snapshots+' · observation '+counts.observations+' · source '+counts.sources:'尚未讀取 stage';
      by('labOutput').textContent=state.result&&!state.editing?JSON.stringify(state.result,null,2):state.result?'已返回編輯；先前結果可由重新讀取的 stage 與操作證據核對。':'尚未取得本次操作輸出。';
      by('labEvidence').textContent=JSON.stringify(state.server?{version:state.server.version,test_evidence:state.server.test_evidence,operations:state.server.operations,stage:state.server.stage,limits:state.server.limits}:{status:'未連線；HTTP、瀏覽器與視覺 QA 尚未驗證。'},null,2);
      const links=by('labDownloads');links.replaceChildren();
      for(const key of state.server?.artifacts || []){const a=make('a',key==='criteria'?'驗收標準 JSON':key);a.href='/artifact/'+encodeURIComponent(key);a.target='_blank';a.rel='noopener';links.append(a);}
      if(state.result?.artifact_key&&!state.server.artifacts.includes(state.result.artifact_key)){const a=make('a','下載本次 ssr.collection.v1');a.href='/artifact/'+encodeURIComponent(state.result.artifact_key);links.append(a);}
      if(state.server?.criteria!==lastCriteria){lastCriteria=state.server?.criteria;const box=by('labCriteria');box.replaceChildren();for(const c of lastCriteria?.criteria || []){const item=doc.createElement('article');item.className='card';item.append(make('h3',c.id));for(const [label,key] of [['輸入','input'],['預期輸出','expected'],['成功判定','success'],['邊界','boundaries']])item.append(make('strong',label),make('p',c[key]));box.append(item);}
        if(lastCriteria){by('labCommonStatus').textContent=lastCriteria.common_gate.status.toUpperCase()+'：預設瀏覽器實際開啟運作門檻尚未通過。';by('labBrowserEvidence').textContent=JSON.stringify(lastCriteria.common_gate,null,2);by('labVerifiedEvidence').textContent=JSON.stringify(lastCriteria.actual_verified,null,2);for(const [id,items] of [['labNotApplicableList',lastCriteria.not_applicable],['labBlockedList',lastCriteria.unverified_blocked]]){const list=by(id);list.replaceChildren();for(const item of items)list.append(make('li',(item.status?item.status.toUpperCase()+' · ':'')+item.item+'：'+item.reason));}}
      }
    }});
    by('labForm').addEventListener('submit',event=>{event.preventDefault();flow.submit(by('labText').value,by('labFormat').value,by('labConfirm').checked);});
    by('labExample').addEventListener('click',()=>{by('labFormat').value='plain_text';by('labText').value='合成測試：Lunar Rope（月亮繩）不是 PEAK 真實道具。這段虛構文字只驗證 UTF-8、正文、雜湊與私有資料包；SOURCE_COMMAND 僅為文字。';by('labText').focus();});
    by('labClear').addEventListener('click',()=>{if(flow.clear()){by('labText').value='';by('labConfirm').checked=false;by('labText').focus();}});
    by('labBack').addEventListener('click',()=>{if(flow.back())by('labText').focus();});
    by('labReload').addEventListener('click',()=>flow.refresh());by('labNewSession').addEventListener('click',()=>flow.newSession());
    if(offline){by('labConnection').textContent='檔案預覽：未連線，操作未啟用。';by('labReload').disabled=true;by('labCriteriaDoc').href='../docs/collector-independent-criteria.json';}
    else flow.refresh();
    return flow;
  }
  return {createFlow,mount};
});
