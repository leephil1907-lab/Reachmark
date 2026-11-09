import {createContext,useCallback,useContext,useMemo,useState,type ReactNode,useEffect} from 'react';
import {CheckCircle2,AlertCircle,Info,X} from 'lucide-react';
type ToastKind='success'|'error'|'info'; type ToastItem={id:number;kind:ToastKind;message:string};
const C=createContext<{push:(message:string,kind?:ToastKind)=>void}>({push:()=>{}});
export function useToast(){return useContext(C)}
function ToastCard({item,remove}:{item:ToastItem;remove:(id:number)=>void}){
 const [paused,setPaused]=useState(false);
 useEffect(()=>{if(paused)return;const id=window.setTimeout(()=>remove(item.id),4000);return()=>window.clearTimeout(id)},[paused,item.id,remove]);
 return <div className={'toast glass '+item.kind} role="status" onMouseEnter={()=>setPaused(true)} onMouseLeave={()=>setPaused(false)} onFocus={()=>setPaused(true)} onBlur={()=>setPaused(false)}><span className="toast-icon">{item.kind==='success'?<CheckCircle2/>:item.kind==='error'?<AlertCircle/>:<Info/>}</span><span>{item.message}</span><button aria-label="Dismiss notification" onClick={()=>remove(item.id)}><X size={16}/></button><i style={{animationPlayState:paused?'paused':'running'}}/></div>
}
export function ToastProvider({children}:{children:ReactNode}){
 const [items,setItems]=useState<ToastItem[]>([]);
 const remove=useCallback((id:number)=>setItems(v=>v.filter(x=>x.id!==id)),[]);
 const push=useCallback((message:string,kind:ToastKind='info')=>{const id=Date.now()+Math.random();setItems(v=>[...v.slice(-1),{id,kind,message}])},[]);
 const value=useMemo(()=>({push}),[push]);
 return <C.Provider value={value}>{children}<div className="toast-stack" aria-live="polite" aria-relevant="additions"><>{items.map(item=><ToastCard key={item.id} item={item} remove={remove}/>)}</></div></C.Provider>
}
