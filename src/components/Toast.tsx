import {createContext,useCallback,useContext,useMemo,useState,type ReactNode} from 'react';
import {CheckCircle2,AlertCircle,Info,X} from 'lucide-react';
type ToastKind='success'|'error'|'info'; type ToastItem={id:number;kind:ToastKind;message:string};
const C=createContext<{push:(message:string,kind?:ToastKind)=>void}>({push:()=>{}});
export function useToast(){return useContext(C)}
export function ToastProvider({children}:{children:ReactNode}){
 const [items,setItems]=useState<ToastItem[]>([]);
 const push=useCallback((message:string,kind:ToastKind='info')=>{const id=Date.now()+Math.random();setItems(v=>[...v.slice(-1),{id,kind,message}]);window.setTimeout(()=>setItems(v=>v.filter(x=>x.id!==id)),4000)},[]);
 const value=useMemo(()=>({push}),[push]);
 return <C.Provider value={value}>{children}<div className="toast-stack" aria-live="polite" aria-relevant="additions"><AnimateItems items={items} remove={id=>setItems(v=>v.filter(x=>x.id!==id))}/></div></C.Provider>
}
function AnimateItems({items,remove}:{items:ToastItem[];remove:(id:number)=>void}){return <>{items.map(t=><div className={'toast glass '+t.kind} role="status" key={t.id}>{t.kind==='success'?<CheckCircle2/>:t.kind==='error'?<AlertCircle/>:<Info/>}<span>{t.message}</span><button aria-label="Dismiss notification" onClick={()=>remove(t.id)}><X size={16}/></button><i/></div>)}</>}
