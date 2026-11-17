// Read the installed game's Spine runtime; no game assembly is redistributed.
using System;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using Spine;

public class TemplateTextureLoader : TextureLoader {
    public void Load(AtlasPage page, string path) { page.rendererObject = page.name; }
    public void Unload(object value) { }
}

public static class TemplateRuntimeReader {
    static object Value(object value) {
        if (value == null) return null;
        if (value is BoneData) return ((BoneData)value).Name;
        if (value is SlotData) return ((SlotData)value).Name;
        Type t = value.GetType();
        if (value is float) return Convert.ToDouble(value);
        if (t.IsEnum) return value.ToString();
        if (t.IsPrimitive || value is string || value is decimal) return value;
        if (value is IEnumerable) {
            var list = new List<object>();
            foreach (object item in (IEnumerable)value) list.Add(Value(item));
            return list;
        }
        return value.ToString();
    }
    static Dictionary<string,object> Props(object value) {
        var result = new Dictionary<string,object>();
        foreach (var p in value.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
            if (p.CanRead && p.GetIndexParameters().Length == 0 && p.Name != "RendererObject" && p.Name != "Id")
                result[p.Name] = Value(p.GetValue(value, null));
        return result;
    }
    static List<object> Snap(IEnumerable values) {
        var result = new List<object>();
        foreach (object v in values) result.Add(Props(v));
        return result;
    }
    public static Dictionary<string,object> Read(string skelPath, string atlasPath) {
        return ReadPose(skelPath, atlasPath, null, 0);
    }
    public static Dictionary<string,object> ReadPose(string skelPath, string atlasPath, string animationName, float time) {
        var atlas = new Atlas(new StringReader(File.ReadAllText(atlasPath)), "", new TemplateTextureLoader());
        var parser = new SkeletonBinary(new AtlasAttachmentLoader(atlas));
        var data = parser.ReadSkeletonData(skelPath);
        var result = new Dictionary<string,object>();
        result["version"] = data.Version;
        result["bones"] = Snap(data.Bones);
        result["slots"] = Snap(data.Slots);
        result["ik"] = Snap(data.IkConstraints);
        result["transform"] = Snap(data.TransformConstraints);
        result["path"] = Snap(data.PathConstraints);
        var animations = new List<object>();
        foreach (var animation in data.Animations) {
            var events = new List<object>();
            foreach (var timeline in animation.Timelines) {
                var eventTimeline = timeline as EventTimeline;
                if (eventTimeline == null) continue;
                foreach (var ev in eventTimeline.Events)
                    events.Add(new Dictionary<string,object> { {"Name",ev.Data.Name}, {"Time",Convert.ToDouble(ev.Time)}, {"Milliseconds",(int)(ev.Time * 1000)} });
            }
            animations.Add(new Dictionary<string,object> { {"Name",animation.Name}, {"Duration",Convert.ToDouble(animation.Duration)}, {"Milliseconds",(int)(animation.Duration * 1000)}, {"Events",events} });
        }
        result["animations"] = animations;
        var skins = new List<object>();
        foreach (var skin in data.Skins) {
            var attachments = new List<object>();
            foreach (var entry in skin.Attachments) {
                var a = Props(entry.Value);
                a["type"] = entry.Value.GetType().Name;
                a["slot"] = entry.Key.slotIndex;
                a["key"] = entry.Key.name;
                attachments.Add(a);
            }
            skins.Add(new Dictionary<string,object> { {"name",skin.Name}, {"attachments",attachments} });
        }
        result["skins"] = skins;
        var skeleton = new Skeleton(data);
        skeleton.SetToSetupPose();
        if (!String.IsNullOrEmpty(animationName)) {
            var animation = data.FindAnimation(animationName);
            if (animation == null) throw new ArgumentException("Unknown animation: " + animationName);
            animation.Apply(skeleton, 0, time, true, null, 1, MixBlend.Replace, MixDirection.In);
        }
        skeleton.UpdateWorldTransform();
        var worldBones = new List<object>();
        foreach (var bone in skeleton.Bones)
            worldBones.Add(new Dictionary<string,object> {
                {"name",bone.Data.Name}, {"parent",bone.Data.Parent == null ? null : bone.Data.Parent.Name},
                {"x",bone.WorldX}, {"y",bone.WorldY},
                {"endX",bone.WorldX + bone.A * bone.Data.Length},
                {"endY",bone.WorldY + bone.C * bone.Data.Length}
            });
        result["worldBones"] = worldBones;
        var draws = new List<object>();
        foreach (var slot in skeleton.DrawOrder) {
            var a = slot.Attachment;
            if (a == null) continue;
            float[] xy, uv;
            int[] triangles;
            AtlasRegion region;
            float opacity = slot.A;
            if (a is RegionAttachment) {
                var r = (RegionAttachment)a;
                xy = new float[8]; r.ComputeWorldVertices(slot.Bone, xy, 0, 2);
                uv = r.UVs; triangles = new int[] {0,1,2,2,3,0};
                region = (AtlasRegion)r.RendererObject; opacity *= r.A;
            } else if (a is MeshAttachment) {
                var m = (MeshAttachment)a;
                xy = new float[m.WorldVerticesLength]; m.ComputeWorldVertices(slot,xy);
                uv = m.UVs; triangles = m.Triangles;
                region = (AtlasRegion)m.RendererObject; opacity *= m.A;
            } else continue;
            draws.Add(new Dictionary<string,object> {
                {"slot",slot.Data.Name}, {"attachment",a.Name}, {"page",region.page.name},
                {"xy",xy}, {"uv",uv}, {"triangles",triangles}, {"alpha",opacity},
                {"blend",slot.Data.BlendMode.ToString()}
            });
        }
        result["draws"] = draws;
        return result;
    }
}
