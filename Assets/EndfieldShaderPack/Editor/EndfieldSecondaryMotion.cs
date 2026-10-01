// Adapted Verlet spring core: Copyright (c) 2020 VRM Consortium.
// MIT License: Permission is hereby granted, free of charge, to any person
// obtaining a copy of this software and associated documentation files (the
// "Software"), to deal in the Software without restriction, including without
// limitation the rights to use, copy, modify, merge, publish, distribute,
// sublicense, and/or sell copies of the Software, and to permit persons to
// whom the Software is furnished to do so, subject to the following conditions:
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace EndfieldShaderPack
{
    /// <summary>
    /// Offline/editor secondary motion, explicitly NOT the original Endfield solver.
    /// Verlet/rotation core adapted from UniVRM v0.99.4 VRMSpringBoneLogic (MIT).
    /// See docs/implementation/secondary-motion-20261001/ for license and differences.
    /// Fixed simulation ticks use the same animated pose callback for seek/play/export.
    /// Only reviewed, actually weighted long-hair/skirt edges are owned; no fake tips.
    /// </summary>
    public sealed class EndfieldSecondaryMotion : IDisposable
    {
        public const double StepSeconds=1.0/120.0;
        sealed class Joint
        {
            public Transform bone, child;
            public Quaternion rest, output;
            public Vector3 axis, current, previous;
            public float length, stiffness, drag, gravity, maxSwing;
        }
        readonly List<Joint> joints=new List<Joint>();
        readonly Transform head, chest, pelvis, leftThigh, leftCalf, rightThigh, rightCalf;
        readonly Transform[] driven;
        int tick=-1;
        bool disposed;
        public Transform[] DrivenBones => (Transform[])driven.Clone();
        public Vector3[] SimulatedTails
        { get {var result=new Vector3[joints.Count];for(int i=0;i<result.Length;i++) result[i]=joints[i].current;return result;} }
        public float MaxLengthError
        { get {float error=0;foreach(var j in joints)error=Mathf.Max(error,Mathf.Abs(Vector3.Distance(j.bone.position,j.child.position)-j.length));return error;} }
        public EndfieldSecondaryMotion(Transform root)
        {
            if(root==null) throw new ArgumentNullException(nameof(root));
            var map=new Dictionary<string,Transform>();
            foreach(var t in root.GetComponentsInChildren<Transform>(true))
            {
                if(!t.name.StartsWith("Bip001_")&&!t.name.StartsWith("hair_")&&!t.name.StartsWith("skirt_base_"))continue;
                if(!map.TryAdd(t.name,t)) throw new InvalidOperationException("Ambiguous rig name: "+t.name);
            }
            Transform Get(string name) => map.TryGetValue(name,out var t)?t:throw new InvalidOperationException("Missing physics bone: "+name);
            head=Get("Bip001_Head");chest=Get("Bip001_Spine2");pelvis=Get("Bip001_Pelvis");
            leftThigh=Get("Bip001_L_Thigh");leftCalf=Get("Bip001_L_Calf");rightThigh=Get("Bip001_R_Thigh");rightCalf=Get("Bip001_R_Calf");
            var weighted=new HashSet<Transform>();
            foreach(var smr in root.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var bones=smr.bones;
                foreach(var w in smr.sharedMesh.boneWeights)
                {
                    if(w.weight0>0)weighted.Add(bones[w.boneIndex0]);if(w.weight1>0)weighted.Add(bones[w.boneIndex1]);
                    if(w.weight2>0)weighted.Add(bones[w.boneIndex2]);if(w.weight3>0)weighted.Add(bones[w.boneIndex3]);
                }
            }
            void Chain(string prefix,int count,bool hair)
            {
                for(int i=1;i<count;i++)
                {
                    var bone=Get(prefix+i.ToString("D2")+"_jnt");var child=Get(prefix+(i+1).ToString("D2")+"_jnt");
                    if(child.parent!=bone||!weighted.Contains(bone)||!weighted.Contains(child))
                        throw new InvalidOperationException("Not a reviewed weighted edge: "+bone.name);
                    float length=Vector3.Distance(bone.position,child.position);
                    if(!float.IsFinite(length)||length<1e-4f||length>.6f)
                        throw new InvalidOperationException("Invalid weighted bind edge: "+bone.name+" length="+length);
                    var scale=bone.lossyScale;
                    if(Mathf.Abs(scale.x-1)>1e-4f||Mathf.Abs(scale.y-1)>1e-4f||Mathf.Abs(scale.z-1)>1e-4f)
                        throw new InvalidOperationException("Physics currently requires unscaled character bones");
                    joints.Add(new Joint{bone=bone,child=child,rest=bone.localRotation,output=bone.localRotation,
                        axis=child.localPosition.normalized,length=length,stiffness=hair?1.6f:2.2f,
                        drag=hair?.18f:.28f,gravity=hair?.06f:.03f,maxSwing=hair?36:24});
                }
            }
            // The 07 hair / 04 skirt tips are UNWEIGHTED; builder's identity
            // fallback is not a reliable bind position. No guessed end offsets.
            Chain("hair_R_base_a_",6,true);Chain("hair_L_base_a_",6,true);
            foreach(string side in new[]{"R_c","R_b","R_a","M_a","L_c","L_b","L_a"}) Chain("skirt_base_"+side+"_",3,false);
            driven=new Transform[joints.Count];for(int i=0;i<driven.Length;i++)driven[i]=joints[i].bone;
        }
        public void ResetTimeline() {ThrowIfDisposed();RestorePose();tick=-1;}
        public void RestorePose() {foreach(var j in joints)if(j.bone!=null)j.bone.localRotation=j.rest;}
        void ThrowIfDisposed() {if(disposed)throw new ObjectDisposedException(nameof(EndfieldSecondaryMotion));}
        public void Evaluate(double seconds,Action<float> applyAnimatedPose,bool enabled=true)
        {
            ThrowIfDisposed();
            if(!double.IsFinite(seconds)||seconds<0||seconds>int.MaxValue*StepSeconds)
                throw new ArgumentOutOfRangeException(nameof(seconds));
            if(applyAnimatedPose==null)throw new ArgumentNullException(nameof(applyAnimatedPose));
            if(!enabled) {RestorePose();applyAnimatedPose((float)seconds);tick=-1;return;}
            int wanted=(int)Math.Floor(seconds/StepSeconds+1e-6);
            if(wanted<tick)tick=-1;
            if(tick<0)
            {
                RestorePose();applyAnimatedPose(0);
                foreach(var j in joints){j.current=j.previous=j.child.position;j.output=j.rest;}
                tick=0;
            }
            while(tick<wanted)
            {
                RestorePose();applyAnimatedPose((float)((tick+1)*StepSeconds));
                Step((float)StepSeconds);tick++;
            }
            // Fractional body/camera time must not inject an extra variable physics step.
            RestorePose();applyAnimatedPose((float)seconds);
            foreach(var j in joints)j.bone.localRotation=j.output;
        }
        void Step(float dt)
        {
            foreach(var j in joints)
            {
                Quaternion restWorld=(j.bone.parent!=null?j.bone.parent.rotation:Quaternion.identity)*j.rest;
                Vector3 restDirection=restWorld*j.axis;
                // UniVRM Verlet recurrence: inertia + rest-axis stiffness + gravity.
                Vector3 next=j.current+(j.current-j.previous)*(1-j.drag)+restDirection*(j.stiffness*dt)+Vector3.down*(j.gravity*dt);
                Vector3 origin=j.bone.position;
                next=origin+SafeDirection(next-origin,restDirection)*j.length;
                // Conservative anatomy spheres, authored preview defaults, not extracted constants.
                for(int iteration=0;iteration<3;iteration++)
                {
                    next=ProjectOutsideSphere(origin,j.length,next,head.position+Vector3.up*.055f,.085f);
                    next=ProjectOutsideSphere(origin,j.length,next,chest.position,.125f);
                    next=ProjectOutsideSphere(origin,j.length,next,pelvis.position,.115f);
                    next=ProjectOutsideSphere(origin,j.length,next,(leftThigh.position+leftCalf.position)*.5f,.08f);
                    next=ProjectOutsideSphere(origin,j.length,next,(rightThigh.position+rightCalf.position)*.5f,.08f);
                }
                // A safety cone prevents flips; collisions may conflict with this bound.
                // No promise of mesh-level / all-pose collision-free cloth is made.
                Vector3 direction=Vector3.RotateTowards(restDirection,(next-origin).normalized,j.maxSwing*Mathf.Deg2Rad,0);
                next=origin+direction*j.length;
                j.previous=j.current;j.current=next;
                j.bone.rotation=Quaternion.FromToRotation(restDirection,direction)*restWorld;
                j.output=j.bone.localRotation;
                if(!float.IsFinite(j.output.x+j.output.y+j.output.z+j.output.w))
                    throw new InvalidOperationException("Nonfinite secondary motion: "+j.bone.name);
            }
        }
        static Vector3 SafeDirection(Vector3 value,Vector3 fallback)
        {return value.sqrMagnitude>1e-12f?value.normalized:fallback.normalized;}
        /// <summary>Project onto intersection of length sphere and exterior of collision sphere.
        /// Unlike push-out then normalize, this preserves non-penetration when feasible.
        /// An entirely enclosed segment has no feasible solution: leave it bounded.</summary>
        public static Vector3 ProjectOutsideSphere(Vector3 origin,float length,Vector3 point,Vector3 center,float radius)
        {
            if(!float.IsFinite(length)||length<=0||!float.IsFinite(radius)||radius<0||
                !float.IsFinite(origin.x+origin.y+origin.z+point.x+point.y+point.z+center.x+center.y+center.z))
                throw new ArgumentOutOfRangeException(nameof(length),"Finite positive length / nonnegative radius required");
            Vector3 u=SafeDirection(point-origin,Vector3.up),delta=center-origin;float d=delta.magnitude;
            if(d<1e-7f)return origin+u*length;
            float bound=(length*length+d*d-radius*radius)/(2*length*d);
            Vector3 n=delta/d;
            if(bound>=1||Vector3.Dot(u,n)<=bound||bound<=-1)return origin+u*length;
            Vector3 tangent=u-n*Vector3.Dot(u,n);
            if(tangent.sqrMagnitude<1e-12f)tangent=Vector3.Cross(n,Mathf.Abs(n.x)<.9f?Vector3.right:Vector3.up);
            return origin+(n*bound+tangent.normalized*Mathf.Sqrt(Mathf.Max(0,1-bound*bound)))*length;
        }
        public void Dispose() {if(disposed)return;RestorePose();disposed=true;}
    }
}
