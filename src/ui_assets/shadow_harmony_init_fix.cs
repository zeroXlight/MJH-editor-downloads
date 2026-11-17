using System;using System.Linq;using Mono.Cecil;using Mono.Cecil.Cil;
public static class FixHarmonyInit {
 public static void Patch(string path,string output) {
  var resolver=new DefaultAssemblyResolver();resolver.AddSearchDirectory(System.IO.Path.GetDirectoryName(path));
  using(var a=AssemblyDefinition.ReadAssembly(path,new ReaderParameters{AssemblyResolver=resolver})) {
   var m=a.MainModule;var t=m.Types.Single(x=>x.Name=="StackTraceFixes");var f=t.Methods.Single(x=>x.Name=="Install");var il=f.Body.GetILProcessor();f.Body.InitLocals=true;
   var constructors=f.Body.Instructions.Where(x=>x.OpCode==OpCodes.Newobj&&((MethodReference)x.Operand).DeclaringType.Name.Contains("Detour")).ToArray();
   if(constructors.Length!=3)throw new Exception("Unknown constructor shape");
   foreach(var ins in constructors) {
    var old=(MethodReference)ins.Operand;var dt=old.DeclaringType.Resolve();
    var ct=dt.Methods.Single(x=>x.IsConstructor&&x.Parameters.Count==3&&x.Parameters[0].ParameterType.FullName==old.Parameters[0].ParameterType.FullName&&x.Parameters[1].ParameterType.FullName==old.Parameters[1].ParameterType.FullName&&x.Parameters[2].ParameterType.IsByReference);
    var config=((ByReferenceType)ct.Parameters[2].ParameterType).ElementType;var variable=new VariableDefinition(m.ImportReference(config));var det=new VariableDefinition(m.ImportReference(old.DeclaringType));f.Body.Variables.Add(variable);f.Body.Variables.Add(det);
    var field=config.Resolve().Fields.Single(x=>x.Name=="ManualApply");
    il.InsertBefore(ins,il.Create(OpCodes.Ldloca,variable));il.InsertBefore(ins,il.Create(OpCodes.Initobj,m.ImportReference(config)));
    il.InsertBefore(ins,il.Create(OpCodes.Ldloca,variable));il.InsertBefore(ins,il.Create(OpCodes.Ldc_I4_1));il.InsertBefore(ins,il.Create(OpCodes.Stfld,m.ImportReference(field)));il.InsertBefore(ins,il.Create(OpCodes.Ldloca,variable));
    ins.Operand=m.ImportReference(ct);var dup=il.Create(OpCodes.Dup);il.InsertAfter(ins,dup);il.InsertAfter(dup,il.Create(OpCodes.Stloc,det));
    var store=ins;while(store!=null&&store.OpCode!=OpCodes.Stsfld)store=store.Next;if(store==null)throw new Exception("Missing continuation");
    var load=il.Create(OpCodes.Ldloc,det);il.InsertAfter(store,load);il.InsertAfter(load,il.Create(OpCodes.Callvirt,m.ImportReference(dt.Methods.Single(x=>x.Name=="Apply"&&x.Parameters.Count==0))));
   }
   // Widen original short branches after inserting instructions.
   foreach(var ins in f.Body.Instructions) { if(ins.OpCode==OpCodes.Brfalse_S)ins.OpCode=OpCodes.Brfalse;else if(ins.OpCode==OpCodes.Leave_S)ins.OpCode=OpCodes.Leave; }
   a.Write(output);
  }
 }
}
