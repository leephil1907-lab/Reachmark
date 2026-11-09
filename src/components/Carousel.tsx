import {useEffect,useRef,useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'framer-motion';
import {ArrowLeft,ArrowRight,ArrowUpRight,GripHorizontal} from 'lucide-react';
import {projects} from '../content';
import {Link} from 'react-router-dom';
export default function Carousel(){const [index,setIndex]=useState(0),[paused,setPaused]=useState(false);const reduced=useReducedMotion();const start=useRef(0);const active=projects[index%projects.length];
 const next=(d:number)=>setIndex(v=>(v+d+projects.length)%projects.length);
 useEffect(()=>{if(paused||reduced)return;const t=window.setInterval(()=>next(1),6000);return()=>clearInterval(t)},[paused,reduced]);
 useEffect(()=>{const f=(e:KeyboardEvent)=>{if(e.key==='ArrowRight')next(1);if(e.key==='ArrowLeft')next(-1)};window.addEventListener('keydown',f);return()=>window.removeEventListener('keydown',f)},[]);
 return <div className="featured-carousel glass" role="region" aria-roledescription="carousel" aria-label="Featured Reachmark work" onMouseEnter={()=>setPaused(true)} onMouseLeave={()=>setPaused(false)} onFocus={()=>setPaused(true)} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))setPaused(false)}} onTouchStart={()=>setPaused(true)} onTouchEnd={()=>setPaused(false)}>
  <div className="carousel-top"><span className="eyebrow">SELECTED WORK · {String(index+1).padStart(2,'0')} / {projects.length}</span><span className="drag-hint"><GripHorizontal size={14}/> Drag to explore</span></div>
  <div className="carousel-viewport"><AnimatePresence mode="wait" custom={1}><motion.article key={active.slug} className={'feature-slide '+active.accent} initial={reduced?false:{opacity:0,x:24,filter:'blur(8px)'}} animate={{opacity:1,x:0,filter:'blur(0px)'}} exit={reduced?{opacity:0}:{opacity:0,x:-24,filter:'blur(8px)'}} transition={{duration:.38,ease:[.22,1,.36,1]}} drag="x" dragConstraints={{left:0,right:0}} dragElastic={.15} onDragStart={()=>{start.current=0}} onDragEnd={(_,info)=>{if(info.offset.x<-55||info.velocity.x<-450)next(1);else if(info.offset.x>55||info.velocity.x>450)next(-1)}}>
   <div className="feature-art"><div className="art-glow"/><div className="art-window"><div className="art-window-top"><span/><span/><span/></div><div className="art-ui"><div className="art-side"/><div className="art-main"><i/><b/><b/><div className="art-chart"><span/><span/><span/><span/><span/><span/></div><div className="art-actions"><i/><i/><i/></div></div></div></div><span className="art-tag">{active.type}</span></div>
   <div className="feature-copy"><span className="eyebrow">{active.kind==='concept'?'CONCEPT EXPLORATION':'FEATURED PROJECT'}</span><h3>{active.name}</h3><p>{active.summary}</p><div className="feature-bottom"><span className="metric-chip">{active.metric}</span><Link to={'/work/'+active.slug}>View case study <ArrowUpRight size={15}/></Link></div></div>
  </motion.article></AnimatePresence></div>
  <div className="carousel-controls"><div className="carousel-dots">{projects.slice(0,6).map((p,i)=><button key={p.slug} aria-label={'Show slide '+(i+1)} aria-current={index===i?'true':undefined} onClick={()=>setIndex(i)}><span/></button>)}</div><div className="carousel-buttons"><button className="icon-button" onClick={()=>next(-1)} aria-label="Previous project"><ArrowLeft/></button><button className="icon-button" onClick={()=>next(1)} aria-label="Next project"><ArrowRight/></button></div></div><div className="carousel-progress"><i key={index} style={{animationPlayState:paused?'paused':'running'}}/></div>
 </div>
}
