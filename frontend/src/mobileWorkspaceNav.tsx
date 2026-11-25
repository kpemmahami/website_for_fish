import {useEffect, useRef, useState, type ReactNode} from 'react';
import {Bell, Menu, UserCircle, Waves, X} from 'lucide-react';

export function MobileWorkspaceNav({title, navigation, accountName, overdueLoans, overdueFeeding, signOut}: {
  title: string;
  navigation: ReactNode;
  accountName: string;
  overdueLoans: number;
  overdueFeeding: number;
  signOut: () => void;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(()=>{
    if(!open)return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const viewport = window.matchMedia('(max-width: 800px)');
    const close = ()=>drawer.current?.close();
    const handleResize = ()=>{if(!viewport.matches)close()};
    viewport.addEventListener('change',handleResize);
    window.addEventListener('popstate',close);
    window.addEventListener('hashchange',close);
    handleResize();
    return ()=>{
      document.body.style.overflow = previousOverflow;
      viewport.removeEventListener('change',handleResize);
      window.removeEventListener('popstate',close);
      window.removeEventListener('hashchange',close);
    };
  },[open]);

  return <>
    <div className="mobile-workspace-header">
      <button type="button" className="outline mobile-header-icon" ref={trigger} aria-label="Open navigation"
        aria-controls="mobile-workspace-drawer" aria-expanded={open} onClick={()=>{
          drawer.current?.showModal();
          setOpen(true);
        }}><Menu size={22} aria-hidden="true"/></button>
      <div className="mobile-workspace-brand">
        <Waves size={22} aria-hidden="true"/>
        <div><b>AquaFarm</b><small>{title}</small></div>
      </div>
      <details className="mobile-header-menu">
        <summary className="outline mobile-header-icon" aria-label="Notifications">
          <Bell size={20} aria-hidden="true"/>
          {overdueLoans+overdueFeeding>0&&<span className="mobile-alert-dot" aria-hidden="true"/>}
        </summary>
        <div className="mobile-header-popover">
          {overdueFeeding>0&&<p>{overdueFeeding} feeding {overdueFeeding===1?'record overdue':'records overdue'}</p>}
          {overdueLoans>0&&<p>{overdueLoans} loan {overdueLoans===1?'instalment overdue':'instalments overdue'}</p>}
          {overdueLoans+overdueFeeding===0&&<p>No overdue alerts.</p>}
        </div>
      </details>
      <details className="mobile-header-menu">
        <summary className="outline mobile-header-icon" aria-label="Account menu"><UserCircle size={21} aria-hidden="true"/></summary>
        <div className="mobile-header-popover"><p>{accountName}</p>
          <button type="button" className="outline" onClick={signOut}>Sign out</button>
        </div>
      </details>
    </div>
    <dialog id="mobile-workspace-drawer" className="mobile-workspace-drawer" ref={drawer} aria-label="Workspace navigation"
      onClose={()=>{setOpen(false);trigger.current?.focus()}}
      onClick={event=>{if(event.target===event.currentTarget)drawer.current?.close()}}>
      <aside className="sidebar">
        <div className="mobile-drawer-heading"><b>AquaFarm Manager Ghana</b>
          <button type="button" className="outline mobile-header-icon" autoFocus aria-label="Close navigation"
            onClick={()=>drawer.current?.close()}><X size={21} aria-hidden="true"/></button>
        </div>
        <div className="navlabel">WORKSPACE</div>
        <div onClick={event=>{
          const button = (event.target as HTMLElement).closest('button');
          if(!button||button.dataset.keepDrawerOpen==='true')return;
          drawer.current?.close();
          window.scrollTo({top:0});
        }}>{navigation}</div>
        <button type="button" className="outline mobile-drawer-signout" onClick={signOut}>Sign out</button>
      </aside>
    </dialog>
  </>;
}
