import {useEffect,useRef,useState} from 'react';
import {motion,useReducedMotion} from 'framer-motion';
import {ArrowRight,Check,MousePointer2} from 'lucide-react';
export default function Lens(){const ref=useRef<HTMLDivElement>(null);const [pos,setPos]=useState({x:54,y:50});const reduced=useReducedMotion();
 useEffect(()=>{if(reduced)return;const el=ref.current;if(!el)return;let frame=0;const move=(e:PointerEvent)=>{if(e.pointerType==='touch')return;cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{const r=el.getBoundingClientRect();setPos({x:Math.max(8,Math.min(92,(e.clientX-r.left)/r.width*100)),y:Math.max(12,Math.min(88,(e.clientY-r.top)/r.height*100))})})};el.addEventListener('pointermove',move);return()=>{el.removeEventListener('pointermove',move);cancelAnimationFrame(frame)}},[reduced]);
 useEffect(()=>{if(reduced)return;let n=0;const id=window.setInterval(()=>{n++;setPos({x:32+(n%3)*18,y:42+(n%2)*12})},3200);return()=>clearInterval(id)},[reduced]);
 return <div className="lens-stage" ref={ref} aria-label="Illustration of a website review lens">
  <div className="lens-browser glass"><div className="browser-top"><span/><span/><span/><small>northstar.example</small><i>LIVE PAGE · EXAMPLE</i></div><div className="mock-site"><div className="mock-nav"><b>northstar</b><span>Services　 About　 Contact</span><button>Let's talk</button></div><div className="mock-hero"><small>BUILT FOR WHAT'S NEXT</small><h3>Make your next<br/>move <em>matter.</em></h3><p>Clarity for teams ready to grow.</p><button className="mock-weak">Learn more <ArrowRight size={12}/></button></div><div className="mock-cards"><span/><span/><span/></div><div className="leak leak-speed"><i/>Slow first impression</div><div className="leak leak-cta"><i/>Unclear next step</div><div className="leak leak-contrast"><i/>Low contrast</div></div>
   <motion.div className="lens-disc" animate={{left:pos.x+'%',top:pos.y+'%'}} transition={{type:'spring',stiffness:80,damping:24}}><span className="lens-cross"/><span className="lens-ring"/><span className="lens-caption"><MousePointer2 size={12}/> FIND THE LEAK</span></motion.div>
  </div><div className="lens-legend"><span><i className="dot mint"/> Issues worth investigating</span><span><i className="dot blue"/> Evidence-led recommendations</span></div>
 </div>
}
