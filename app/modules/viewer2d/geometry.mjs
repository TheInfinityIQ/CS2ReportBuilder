// Delaunay triangles join nearby burning patch centers without overlapping faces.
const cross = (a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
function circumcircle(a,b,c){
  const d=2*cross(a,b,c);if(Math.abs(d)<1e-8)return null;
  const aa=a.x*a.x+a.y*a.y,bb=b.x*b.x+b.y*b.y,cc=c.x*c.x+c.y*c.y;
  const x=(aa*(b.y-c.y)+bb*(c.y-a.y)+cc*(a.y-b.y))/d;
  const y=(aa*(c.x-b.x)+bb*(a.x-c.x)+cc*(b.x-a.x))/d;
  return {x,y,r2:(x-a.x)**2+(y-a.y)**2};
}
export function fireMesh(patches){
  const seen=new Set(),points=[];
  for(const p of patches){
    if(!p.burning||![p.x,p.y,p.z].every(Number.isFinite))continue;
    const key=`${p.x}:${p.y}`;if(seen.has(key))continue;seen.add(key);points.push(p);
  }
  if(!points.length)return {points,triangles:[],links:[]};
  const n=points.length,xs=points.map(p=>p.x),ys=points.map(p=>p.y);
  const x=(Math.min(...xs)+Math.max(...xs))/2,y=(Math.min(...ys)+Math.max(...ys))/2;
  const span=Math.max(1,Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys))*32;
  const all=[...points,{x:x-span,y:y-span},{x:x+span,y:y-span},{x,y:y+span}];
  let faces=[[n,n+1,n+2]];
  for(let i=0;i<n;i++){
    const edges=new Map(),keep=[];
    for(const face of faces){
      const circle=circumcircle(...face.map(j=>all[j]));
      if(circle&&(all[i].x-circle.x)**2+(all[i].y-circle.y)**2<=circle.r2+1e-6){
        for(let k=0;k<3;k++){
          const a=face[k],b=face[(k+1)%3],key=[a,b].sort((a,b)=>a-b).join(':');
          if(edges.has(key))edges.delete(key);else edges.set(key,[a,b]);
        }
      }else keep.push(face);
    }
    for(const [a,b] of edges.values())keep.push(cross(all[a],all[b],all[i])>0?[a,b,i]:[b,a,i]);
    faces=keep;
  }
  const near=(a,b,limit)=>Math.hypot(points[a].x-points[b].x,points[a].y-points[b].y)<=limit
    &&Math.abs(points[a].z-points[b].z)<=32;
  const triangles=faces.filter(t=>t.every(i=>i<n)&&near(t[0],t[1],96)&&near(t[1],t[2],96)&&near(t[2],t[0],96)
    &&(circumcircle(...t.map(i=>points[i]))?.r2??Infinity)<=64**2);
  // Short links also cover sparse/two-point/collinear clusters.
  const links=[];
  for(let a=0;a<n;a++)for(let b=a+1;b<n;b++)if(near(a,b,64))links.push([a,b]);
  return {points,triangles,links};
}
