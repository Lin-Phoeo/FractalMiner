using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using EndfieldShaderPack.EditorTools.Mmd;
using Object = UnityEngine.Object;

namespace EndfieldShaderPack
{
    // Reflection lets the missing implementation fail at runtime, not compilation.
    public static class EndfieldSecondaryMotionValidation
    {
        static readonly List<string> lines = new List<string>();
        static int checks;
        static Type solverType;
        static void Check(bool ok, string why)
        { if (!ok) throw new InvalidOperationException(why); checks++; lines.Add("PASS " + why); }
        static void Evaluate(object solver, double t, Action<float> pose, bool enabled = true)
        { solverType.GetMethod("Evaluate").Invoke(solver, new object[]{t, pose, enabled}); }
        static Transform[] Bones(object solver) => (Transform[])solverType.GetProperty("DrivenBones").GetValue(solver);
        static Quaternion[] Rotations(Transform[] bones)
        { var result=new Quaternion[bones.Length]; for(int i=0;i<bones.Length;i++) result[i]=bones[i].localRotation; return result; }
        static float Difference(Quaternion[] a, Quaternion[] b)
        { float max=0;for(int i=0;i<a.Length;i++) max=Mathf.Max(max,Quaternion.Angle(a[i],b[i]));return max; }
        public static void RunBatch()
        {
            string output=Environment.GetEnvironmentVariable("ENDFIELD_PHYSICS_OUTPUT") ?? "Validation/secondary-motion-20261001-01";
            if(Directory.Exists(output)) throw new IOException("Fresh output required");
            Directory.CreateDirectory(output); lines.Clear();checks=0;
            try
            {
                solverType=typeof(EndfieldSecondaryMotionValidation).Assembly.GetType("EndfieldShaderPack.EndfieldSecondaryMotion");
                Check(solverType!=null,"secondary-motion implementation exists");
                using(var session=new EndfieldWetnessSession(true))
                {
                    session.InitializeMmdPose();session.FrameFront();
                    var profile=MmdRetargetProfile.FromUnity(session.Root);
                    var head=profile.ByRole(10).transform;
                    var baseHead=head.localRotation;
                    var all=session.Root.GetComponentsInChildren<Transform>(true);
                    var before=Rotations(all);
                    object solver=Activator.CreateInstance(solverType,new object[]{session.Root});
                    try
                    {
                        var bones=Bones(solver);var rest=Rotations(bones);
                        Check(bones.Length==30,"exact reviewed 10 long-hair + 14 skirt + 6 tail joints; unweighted tips excluded");
                        foreach(var bone in bones) Check(bone.name.StartsWith("hair_")||bone.name.StartsWith("skirt_base_")||bone.name.StartsWith("tail_M_stone_a_"),"secondary-only ownership "+bone.name);
                        Action<float> pose=t=>head.localRotation=baseHead*Quaternion.Euler(0,30*Mathf.Sin(t*4),0);
                        Evaluate(solver,1,pose);
                        var direct=Rotations(bones);
                        Check(Difference(rest,direct)>1,"animated head produces measurable hair/skirt secondary rotation");
                        Check(Quaternion.Angle(head.localRotation,baseHead*Quaternion.Euler(0,30*Mathf.Sin(4),0))<.001f,"solver does not overwrite primary animated head");
                        Evaluate(solver,0,pose);
                        for(int i=1;i<=100;i++) Evaluate(solver,i/100.0,pose);
                        Check(Difference(direct,Rotations(bones))<.05f,"direct seek and incremental playback agree at fixed 120 Hz");
                        var frozen=Rotations(bones);Evaluate(solver,1,pose);
                        Check(Difference(frozen,Rotations(bones))<.05f,"repeat same timestamp does not advance simulation");
                        Evaluate(solver,.35,pose);Evaluate(solver,1,pose);
                        Check(Difference(direct,Rotations(bones))<.05f,"backward scrub replays deterministically from zero");
                        foreach(int fps in new[]{30,60})
                        {
                            Evaluate(solver,0,pose);
                            for(int i=1;i<=fps;i++)Evaluate(solver,(double)i/fps,pose);
                            Check(Difference(direct,Rotations(bones))<.05f,"same 120Hz result from "+fps+"fps sampling");
                        }
                        Evaluate(solver,1,pose,false);
                        Check(Difference(rest,Rotations(bones))<.05f,"disable removes simulated local rotations immediately");
                        Evaluate(solver,1,pose);
                        Check(Difference(direct,Rotations(bones))<.05f,"re-enable reconstructs timeline, not dirty physical rest");
                        Evaluate(solver,20,pose);
                        var tails=(Vector3[])solverType.GetProperty("SimulatedTails").GetValue(solver);
                        for(int i=0;i<bones.Length;i++)
                        {
                            Check(float.IsFinite(tails[i].x+tails[i].y+tails[i].z),"finite after 2400 substeps "+bones[i].name);
                            Check(Quaternion.Angle(rest[i],bones[i].localRotation)<=36.01f,"bounded swing "+bones[i].name);
                        }
                        Check((float)solverType.GetProperty("MaxLengthError").GetValue(solver)<2e-5f,"fixed segment length after long run");
                        foreach(double invalid in new[]{double.NaN,double.PositiveInfinity,-1.0})
                        {
                            bool rejected=false;try {Evaluate(solver,invalid,pose);} catch(TargetInvocationException e) {rejected=e.InnerException is ArgumentOutOfRangeException;}
                            Check(rejected,"invalid timestamp rejected before pose writes: "+invalid);
                        }
                        var project=solverType.GetMethod("ProjectOutsideSphere",BindingFlags.Public|BindingFlags.Static);
                        Vector3 projected=(Vector3)project.Invoke(null,new object[]{Vector3.zero,1f,new Vector3(0,1,0),new Vector3(0,1,0),.5f});
                        Check(Mathf.Abs(projected.magnitude-1)<2e-6f&&Vector3.Distance(projected,Vector3.up)>=.49999f,"collision projection preserves both bone length and sphere exclusion");
                        bool invalidSphere=false;
                        try {project.Invoke(null,new object[]{Vector3.zero,0f,Vector3.up,Vector3.up,.5f});}
                        catch(TargetInvocationException e){invalidSphere=e.InnerException is ArgumentOutOfRangeException;}
                        Check(invalidSphere,"zero length collision input rejected");
                        string motion=Environment.GetEnvironmentVariable("ENDFIELD_MMD_TEST_MOTION");
                        if(string.IsNullOrEmpty(motion)) throw new IOException("Real VMD fixture required");
                        head.localRotation=baseHead;
                        Evaluate(solver,0,t=>{},false);
                        var player=MmdPlayer.Load(Vmd.ReadFile(motion),session.Root);
                        Check(player.calibrationOk,"actual VMD calibration before physics");
                        Action<float> mmd=t=>{player.Reset();player.ApplyFrame(t,player.suggestedScale,true,0);};
                        Evaluate(solver,0,mmd,false);
                        Evaluate(solver,2,mmd,false);
                        session.SavePreview(Path.Combine(output,"01-mmd-no-physics.png"));
                        var smrs=session.Root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                        var dryVertices=new Dictionary<SkinnedMeshRenderer,Vector3[]>();
                        foreach(var smr in smrs) {var mesh=new Mesh();smr.BakeMesh(mesh);dryVertices[smr]=mesh.vertices;Object.DestroyImmediate(mesh);}
                        Evaluate(solver,2,mmd);
                        int movedMeshes=0;
                        foreach(var smr in smrs)
                        {
                            var mesh=new Mesh();smr.BakeMesh(mesh);float max=0;var v=mesh.vertices;
                            for(int i=0;i<v.Length;i++) max=Mathf.Max(max,Vector3.Distance(v[i],dryVertices[smr][i]));
                            if(max>.001f) movedMeshes++;
                            if(smr.name=="S_actor_typhoea_cloth_04_lod0")
                                Check(max>.001f,"weighted tail cloth04 actually deforms, not only unused helper bones");
                            // A weighted descendant follows a driven ancestor even
                            // when that ancestor is not directly in this mesh palette.
                            bool ownedMesh=false;
                            foreach(var bone in smr.bones)
                                for(var ancestor=bone;ancestor!=null&&ancestor!=session.Root.parent;ancestor=ancestor.parent)
                                    ownedMesh|=Array.IndexOf(bones,ancestor)>=0;
                            if(!ownedMesh)Check(max<1e-6f,"secondary motion does not deform unrelated mesh "+smr.name);
                            lines.Add("MESH "+smr.name+" maxDisplacement="+max.ToString("R"));Object.DestroyImmediate(mesh);
                        }
                        Check(movedMeshes>=2,"real weighted hair/skirt mesh vertices move, not only unused helper bones");
                        session.SavePreview(Path.Combine(output,"02-mmd-physics.png"));
                        session.Weather.wetEnabled=true;session.Weather.freezeTime=true;
                        session.SavePreview(Path.Combine(output,"03-mmd-physics-wet.png"));
                        string frames=Path.Combine(output,"frames");Directory.CreateDirectory(frames);
                        for(int k=0;k<=60;k++)
                        {
                            Evaluate(solver,k/30.0,mmd);
                            session.SavePreview(Path.Combine(frames,"frame_"+k.ToString("D4")+".png"),960,600);
                        }
                        for(float t=0;t<=(float)player.clip.Duration;t+=.5f)
                        {
                            Evaluate(solver,t,mmd);bool finite=true;
                            foreach(var bone in all)finite&=float.IsFinite(bone.rotation.x+bone.rotation.y+bone.rotation.z+bone.rotation.w);
                            Check(finite&&((float)solverType.GetProperty("MaxLengthError").GetValue(solver)<2e-5f),"actual VMD half-second samples finite/fixed lengths t="+t.ToString("F1"));
                        }
                        Evaluate(solver,player.clip.Duration,mmd);
                        Check((float)solverType.GetProperty("MaxLengthError").GetValue(solver)<2e-5f,"actual VMD final timestamp fixed lengths");
                        foreach(var t in all) Check(float.IsFinite(t.rotation.x+t.rotation.y+t.rotation.z+t.rotation.w),"real VMD/physics finite "+t.name);
                    }
                    finally {((IDisposable)solver).Dispose();head.localRotation=baseHead;}
                    // MMD changes body legitimately; only secondary locals must restore.
                    var selected=(Transform[])solverType.GetProperty("DrivenBones").GetValue(solver);
                    foreach(var bone in selected)
                    {int i=Array.IndexOf(all,bone);Check(Quaternion.Angle(bone.localRotation,before[i])<.05f,"dispose restores owned joint "+bone.name);}
                }
                VerifyStudio(output);
                lines.Add("RESULT PASS checks="+checks+"; alternate secondary physics, NOT certified official solver.");
                File.WriteAllLines(Path.Combine(output,"report.txt"),lines);
            }
            catch(Exception error) {lines.Add("FAIL "+error);File.WriteAllLines(Path.Combine(output,"report.txt"),lines);throw;}
            finally {EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);}
        }
        static void VerifyStudio(string output)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            var window=ScriptableObject.CreateInstance<EndfieldMmdStudio>();
            var flags=BindingFlags.Instance|BindingFlags.NonPublic;
            object Field(string name)=>typeof(EndfieldMmdStudio).GetField(name,flags).GetValue(window);
            void Set(string name,object value)=>typeof(EndfieldMmdStudio).GetField(name,flags).SetValue(window,value);
            object Call(string name,params object[] args)=>typeof(EndfieldMmdStudio).GetMethod(name,flags).Invoke(window,args);
            try
            {
                // In-memory test settings only; do not overwrite user's EditorPrefs.
                Set("sourceRigJsonPath","");
                Call("LoadMotion",Environment.GetEnvironmentVariable("ENDFIELD_MMD_TEST_MOTION"));
                Check(Field("player")!=null&&Field("secondaryMotion")!=null,"actual MMD Studio load creates shared physics session");
                Set("camDrive",false);Set("keepFeetAboveFloor",false);
                Call("ApplyAt",2f);
                var solver=Field("secondaryMotion");var first=Rotations(Bones(solver));
                Set("ampHead",.5f);Call("ApplyAt",2f);
                var changed=Rotations(Bones(solver));
                Set("ampHead",1f);Call("ApplyAt",2f);
                Check(Difference(first,Rotations(Bones(solver)))<.05f,"Studio parameter change invalidates previous physics history");
                Check(Difference(first,changed)>.01f,"actual head-amplitude change affects replayed physics");
                Set("keepFeetAboveFloor",true);Call("ApplyAt",2f);
                Check((float)solverType.GetProperty("MaxLengthError").GetValue(solver)<2e-5f,"Studio floor correction and physics preserve segment lengths");
                Set("keepFeetAboveFloor",false);Call("ApplyAt",2f);
                Check(Difference(first,Rotations(Bones(solver)))<.05f,"Studio floor-option change reconstructs physical history");
                var session=(EndfieldWetnessSession)Field("renderSession");session.FrameFront();
                session.SavePreview(Path.Combine(output,"04-studio-preview.png"));
                var routine=(System.Collections.IEnumerator)Call("RunRender",1,2f);
                try
                {
                    Check(routine.MoveNext(),"actual Studio export begins");
                    Check(routine.MoveNext(),"actual Studio export writes frame");
                    Check(Difference(first,Rotations(Bones(solver)))<.05f,"actual export uses same physics state as preview");
                }
                finally{(routine as IDisposable)?.Dispose();}
                var mesh=session.Root.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                Object.DestroyImmediate(window);window=null;
                foreach(var smr in mesh)Check(!smr.sharedMesh.name.Contains("wet rest streams"),"Studio close restores original mesh "+smr.name);
            }
            finally {if(window!=null)Object.DestroyImmediate(window);}
        }
    }
}
