// TIA Openness CAx Export (V20 / V21)
// 将当前打开的 Portal 工程硬件导出为 AML，供 scripts/aml_to_cabinet.py 转成柜配置 JSON。
//
// 要求：
// - 已安装 TIA Portal V20 或 V21 + Openness
// - 当前用户在 Windows 组「Siemens TIA Openness」中（或程序已签名）
// - 工程已在 Portal 中打开，或通过 --project 指定 .ap20 / .ap21 路径
//
// 引用 DLL 默认路径（可用环境变量 TIA_PUBLICAPI 覆盖）：
//   V21: ...\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Base.dll (+ Step7)
//   V20: ...\Portal V20\PublicAPI\V20\Siemens.Engineering.dll

using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;

namespace CheckPlc.TiaExport
{
    internal static class Program
    {
        private static readonly List<string> ProbeDirs = new List<string>();

        private static int Main(string[] args)
        {
            // Siemens 异常有时 ToString() 会再崩，先挂全局兜底
            AppDomain.CurrentDomain.UnhandledException += (_, e) =>
            {
                try
                {
                    var ex = e.ExceptionObject as Exception;
                    Console.Error.WriteLine("未处理异常: " + (ex != null ? ex.GetType().FullName : e.ExceptionObject));
                    if (ex != null)
                        Console.Error.WriteLine(SafeMessage(ex));
                }
                catch
                {
                    Console.Error.WriteLine("未处理异常（无法读取详情）");
                }
            };

            SetupAssemblyResolve();

            string projectPath = null;
            string outAml = Path.Combine(Environment.CurrentDirectory, "export.aml");
            string deviceName = null; // null = 导出整个工程
            bool attach = true;

            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if ((a == "--project" || a == "-p") && i + 1 < args.Length)
                    projectPath = args[++i];
                else if ((a == "--out" || a == "-o") && i + 1 < args.Length)
                    outAml = args[++i];
                else if ((a == "--device" || a == "-d") && i + 1 < args.Length)
                    deviceName = args[++i];
                else if (a == "--new")
                    attach = false;
                else if (a == "--help" || a == "-h")
                {
                    PrintHelp();
                    return 0;
                }
            }

            Console.WriteLine("Openness 探测目录:");
            foreach (string d in ProbeDirs)
                Console.WriteLine("  " + d);

            if (attach)
                Console.WriteLine("模式: 附加已打开的 Portal（请先打开目标工程；中文工程名一般可用）");
            else
                Console.WriteLine("模式: --new 启动无界面 Portal（较慢；建议改用已打开实例）");

            // 单独类型，避免 --help 时 JIT/加载 Siemens.Engineering.*
            return CaxExporter.Run(projectPath, outAml, deviceName, attach);
        }

        private static void SetupAssemblyResolve()
        {
            string envApi = Environment.GetEnvironmentVariable("TIA_PUBLICAPI");
            AddProbe(envApi);

            // x86 进程下 SpecialFolder.ProgramFiles 会变成 Program Files (x86)，
            // 而 Portal 通常装在 64 位 Program Files，两处都探。
            var roots = new[]
            {
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                Environment.GetEnvironmentVariable("ProgramW6432"),
                Environment.GetEnvironmentVariable("ProgramFiles"),
                @"C:\Program Files",
                @"C:\Program Files (x86)",
            };
            foreach (string root in roots)
            {
                if (string.IsNullOrWhiteSpace(root)) continue;
                // V21：API 在 PublicAPI\V21\net48，依赖 Contract 等在 Bin\PublicAPI
                AddProbe(Path.Combine(root, @"Siemens\Automation\Portal V21\PublicAPI\V21\net48"));
                AddProbe(Path.Combine(root, @"Siemens\Automation\Portal V21\Bin\PublicAPI"));
                AddProbe(Path.Combine(root, @"Siemens\Automation\Portal V21\Bin"));
                // V20
                AddProbe(Path.Combine(root, @"Siemens\Automation\Portal V20\PublicAPI\V20"));
                AddProbe(Path.Combine(root, @"Siemens\Automation\Portal V20\Bin\PublicAPI"));
                AddProbe(Path.Combine(root, @"Siemens\Automation\Portal V20\Bin"));
            }

            AppDomain.CurrentDomain.AssemblyResolve += (_, args) =>
            {
                try
                {
                    string name = new AssemblyName(args.Name).Name + ".dll";
                    foreach (string dir in ProbeDirs)
                    {
                        string path = Path.Combine(dir, name);
                        if (File.Exists(path))
                            return Assembly.LoadFrom(path);
                    }
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine("AssemblyResolve 失败: " + SafeMessage(ex));
                }
                return null;
            };
        }

        private static void AddProbe(string dir)
        {
            if (string.IsNullOrWhiteSpace(dir) || !Directory.Exists(dir))
                return;
            string full = Path.GetFullPath(dir);
            if (!ProbeDirs.Exists(d => string.Equals(d, full, StringComparison.OrdinalIgnoreCase)))
                ProbeDirs.Add(full);
        }

        internal static string SafeMessage(Exception ex)
        {
            if (ex == null) return "";
            try
            {
                string msg = ex.GetType().Name + ": " + ex.Message;
                if (ex.InnerException != null)
                    msg += " | Inner: " + ex.InnerException.GetType().Name + ": " + ex.InnerException.Message;
                return msg;
            }
            catch
            {
                return ex.GetType().FullName ?? "Exception";
            }
        }

        private static void PrintHelp()
        {
            Console.WriteLine(@"CheckPLC TIA Openness CAx Export (V20/V21)

用法:
  CheckPlc.TiaExport.exe [--project path.ap21] [--out export.aml] [--device 站名] [--new]

选项:
  --project, -p   工程 .ap20/.ap21 路径（Portal 未打开工程时需要）
  --out, -o       输出 AML 路径（默认 .\export.aml）
  --device, -d    只导出指定站/设备名（默认导出整个工程）
  --new           强制启动新 Portal，不附加已运行实例
  --help, -h      显示帮助

说明:
  中文工程名/路径一般没问题。若一运行就崩溃且未打印「附加/启动 Portal」，
  多半是 Openness 依赖 DLL 未找到，或本机未打开 Portal / 未加入 Openness 组。
");
        }
    }
}
