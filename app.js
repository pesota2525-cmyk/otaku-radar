
const LABELS={
  goods:"グッズ",figure:"フィギュア",lottery:"くじ・プライズ",collab:"コラボ",
  cosplay:"コスプレ",photo:"女性撮影会",eroge:"PCゲーム特典",bookbonus:"漫画特典",
  doujin:"同人誌",gamers:"ゲーマーズ",trend:"🔥 注目商品"
};
let data=[],cat="all",savedOnly=false;
const saved=new Set(JSON.parse(localStorage.getItem("otakuRadarSavedV3")||"[]"));
const $=s=>document.querySelector(s);
const fmt=d=>{try{return new Intl.DateTimeFormat("ja-JP",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"}).format(new Date(d))}catch{return ""}};

function withinDays(x, days){
  if(days==="all") return true;
  const ms=Number(days)*86400000;
  return (Date.now()-new Date(x.published_at).getTime()) <= ms;
}
function render(){
  const q=$("#search").value.trim().toLowerCase();
  const sort=$("#sort").value;
  const period=$("#period").value;
  let rows=data.filter(x =>
    (cat==="all"||x.category===cat) &&
    (!q || (x.title+" "+x.publisher+" "+(x.meta||"")).toLowerCase().includes(q)) &&
    (!savedOnly||saved.has(x.id)) &&
    withinDays(x,period)
  );

  rows.sort((a,b)=>{
    if(sort==="new") return new Date(b.published_at)-new Date(a.published_at);
    if(sort==="image") return (Number(Boolean(b.image))-Number(Boolean(a.image))) || (b.score-a.score) || (new Date(b.published_at)-new Date(a.published_at));
    return (Number(Boolean(b.direct))-Number(Boolean(a.direct))) || (Number(Boolean(b.image))-Number(Boolean(a.image))) || (b.score-a.score) || (new Date(b.published_at)-new Date(a.published_at));
  });

  const grid=$("#grid"); grid.innerHTML="";
  $("#empty").hidden=rows.length!==0;

  for(const x of rows){
    const frag=$("#cardTemplate").content.cloneNode(true);
    const card=frag.querySelector(".card");
    const imageWrap=frag.querySelector(".imageWrap");
    const img=frag.querySelector("img");
    const title=frag.querySelector(".title");
    imageWrap.href=title.href=x.url;
    if(x.image){
      img.src=x.image; img.alt=x.title;
      img.onerror=()=>{ card.classList.add("noImage"); imageWrap.remove(); };
    }else{
      card.classList.add("noImage");
      imageWrap.remove();
    }
    if(x.direct) card.classList.add("direct");
    frag.querySelector(".badge").textContent=LABELS[x.category]||x.category;
    const source = frag.querySelector(".source");
    source.textContent=(x.direct?"● ":"")+(x.publisher||x.feed_name)+(x.direct?" · 公式/店舗直":" · ニュース");
    title.textContent=x.title;
    const detail=frag.querySelector(".detail");
    detail.textContent=x.meta||"";
    if(!x.meta) detail.remove();
    frag.querySelector("time").textContent=fmt(x.published_at);
    const adult=frag.querySelector(".adultBadge");
    if(x.adult) adult.hidden=false;
    const direct=frag.querySelector(".directBadge");
    if(x.direct) direct.hidden=false;
    const btn=frag.querySelector(".save");
    btn.textContent=saved.has(x.id)?"★":"☆";
    btn.classList.toggle("saved",saved.has(x.id));
    btn.onclick=()=>{
      saved.has(x.id)?saved.delete(x.id):saved.add(x.id);
      localStorage.setItem("otakuRadarSavedV3",JSON.stringify([...saved]));
      render();
    };
    grid.appendChild(frag);
  }
}

fetch("data/items.json?"+Date.now()).then(r=>r.json()).then(j=>{
  data=j.items||[];
  $("#updated").textContent=j.generated_at?`最終更新 ${fmt(j.generated_at)} / ${j.count}件`:"更新待ち";
  render();
}).catch(()=>render());

document.querySelectorAll("#filters button").forEach(b=>b.onclick=()=>{
  document.querySelectorAll("#filters button").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");cat=b.dataset.cat;render();
});
$("#search").oninput=render;
$("#sort").onchange=render;
$("#period").onchange=render;
$("#savedOnly").onclick=e=>{
  savedOnly=!savedOnly;
  e.currentTarget.textContent=savedOnly?"★ 保存中のみ":"★ 保存だけ";
  render();
};
