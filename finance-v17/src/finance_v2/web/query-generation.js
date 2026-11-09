import {createNavigation} from './navigation.js';

// Each visual query flow owns a controller. Separate flows never share its token.
// Reuse route cancellation semantics; request validity includes the parent route.
export function createQueryGeneration(parent=null){
  const queries=createNavigation(()=>parent?.current()??true);
  let active=null;
  return {
    begin(){
      parent?.check();
      const query=queries.begin(),dispose=query.dispose;
      const unlink=parent?.onDispose(()=>query.dispose())||(()=>{});
      query.dispose=()=>{unlink();dispose()};
      active=query;
      return query;
    },
    cancel(){active?.dispose()},
  };
}
