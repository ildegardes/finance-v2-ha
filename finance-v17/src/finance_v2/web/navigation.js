// Shared ownership of a screen's asynchronous work. This never cancels a server write.
export class NavigationCancelled extends Error {
  constructor(){super('NAVIGATION_CANCELLED');this.name='NavigationCancelled'}
}
export const isNavigationCancelled=error=>error instanceof NavigationCancelled;

export function createNavigation(key=()=>location.hash){
  let active=null;
  return {
    begin(){
      active?.dispose();
      const controller=new AbortController(),cleanups=new Set(),routeKey=key();
      const scope={
        signal:controller.signal,
        current:()=>active===scope&&!controller.signal.aborted&&key()===routeKey,
        check(){if(!scope.current())throw new NavigationCancelled()},
        onDispose(fn){
          if(controller.signal.aborted){fn();return ()=>{}}
          cleanups.add(fn);return ()=>cleanups.delete(fn);
        },
        wait(promise,cleanup){
          scope.check();
          return new Promise((resolve,reject)=>{
            let settled=false;
            const finish=(ok,value)=>{
              if(settled)return;settled=true;
              controller.signal.removeEventListener('abort',cancel);
              if(ok)resolve(value);else reject(value);
            };
            const cancel=()=>{
              if(settled)return;
              try{cleanup?.()}finally{finish(false,new NavigationCancelled())}
            };
            controller.signal.addEventListener('abort',cancel,{once:true});
            Promise.resolve(promise).then(value=>{
              if(!scope.current())cancel();else finish(true,value);
            },error=>{
              if(!scope.current())cancel();else finish(false,error);
            });
          });
        },
        run(operation){scope.check();return scope.wait(Promise.resolve().then(()=>{scope.check();return operation()}))},
        dispose(){
          if(controller.signal.aborted)return;
          controller.abort();
          for(const cleanup of cleanups){try{cleanup()}catch(_){/* Detached view cleanup only. */}}
          cleanups.clear();
        },
      };
      active=scope;return scope;
    },
  };
}
