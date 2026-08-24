
const LABELS={goods:"グッズ",figure:"フィギュア",lottery:"くじ・プライズ",collab:"コラボ",cosplay:"コスプレ",photo:"撮影会",eroge:"PCゲーム特典",bookbonus:"漫画特典",doujin:"同人誌",gamers:"ゲーマーズ",trend:"🔥 注目商品"};
let data=[],cat="all",savedOnly=false;
const saved=new Set(JSON.parse(localStorage.getItem("otakuRadarSaved")||"[]"));

const fmt=d=>{try{return new Intl.DateTimeFormat("ja-JP",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}).format(new Date(d))}catch{return ""}};
function render(){
  const q=document.querySelector("#search").value.trim().toLowerCase();
  const sort=document.querySelector("#sort").value;
  let rows=data.filter(x=>(cat==="all"||x.category===cat)&&(!q||(x.title+" "+x.publisher).toLowerCase().includes(q))&&(!savedOnly||saved.has(x.id)));
  rows.sort((a,b)=>sort==="new"?new Date(b.published_at)-new Date(a.published_at):(b.score-a.score)||new Date(b.published_at)-new Date(a.published_at));
  const grid=document.querySelector("#grid"); grid.innerHTML="";
  document.querySelector("#empty").hidden=rows.length!==0;
  for(const x of rows){
    const n=document.querySelector("#cardTemplate").content.cloneNode(true);
    const a=n.querySelector(".imageWrap"), img=n.querySelector("img"), title=n.querySelector(".title");
    a.href=title.href=x.url; img.src=x.image||""; img.alt=x.title; img.onerror=()=>img.remove();
    n.querySelector(".badge").textContent=LABELS[x.category]||x.category;
    n.querySelector(".source").textContent=x.publisher||x.feed_name;
    title.textContent=x.title;
    n.querySelector("time").textContent=fmt(x.published_at);
    const btn=n.querySelector(".save"); btn.textContent=saved.has(x.id)?"★":"☆"; btn.classList.toggle("saved",saved.has(x.id));
    btn.onclick=()=>{saved.has(x.id)?saved.delete(x.id):saved.add(x.id);localStorage.setItem("otakuRadarSaved",JSON.stringify([...saved]));render()};
    grid.appendChild(n);
  }
}
fetch("data/items.json?"+Date.now()).then(r=>r.json()).then(j=>{
  data=j.items||[];
  document.querySelector("#updated").textContent=j.generated_at?`最終更新 ${fmt(j.generated_at)} / ${j.count}件`:"更新待ち";
  render();
}).catch(()=>render());

document.querySelectorAll("#filters button").forEach(b=>b.onclick=()=>{document.querySelectorAll("#filters button").forEach(x=>x.classList.remove("active"));b.classList.add("active");cat=b.dataset.cat;render()});
document.querySelector("#search").oninput=render;
document.querySelector("#sort").onchange=render;
document.querySelector("#savedOnly").onclick=e=>{savedOnly=!savedOnly;e.currentTarget.textContent=savedOnly?"★ 保存中のみ":"★ 保存だけ";render()};
