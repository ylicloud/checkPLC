# TIA Openness CAx Export (V20)
# 将当前打开的 Portal 工程硬件导出为 AML，供 scripts/aml_to_cabinet.py 转成柜配置 JSON。
#
# 要求：
# - 已安装 TIA Portal V20 + Openness
# - 当前用户在 Windows 组「Siemens TIA Openness」中（或程序已签名）
# - 工程已在 Portal 中打开，或通过 --project 指定 .ap20 路径
#
# 引用 DLL 默认路径（可按本机安装位置修改）：
#   C:\Program Files\Siemens\Automation\Portal V20\PublicAPI\V20\Siemens.Engineering.dll

using System;
using System.IO;
using Siemens.Engineering;
using Siemens.Engineering.Cax;
using Siemens.Engineering.HW;

namespace CheckPlc.TiaExport
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
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

            try
            {
                TiaPortal tia = AttachOrStart(attach);
                Project project = OpenOrGetProject(tia, projectPath);
                if (project == null)
                {
                    Console.Error.WriteLine("未找到已打开工程。请先在 Portal 中打开工程，或使用 --project 指定 .ap20。");
                    return 2;
                }

                Console.WriteLine("工程: " + project.Path);
                CaxProvider cax = project.GetService<CaxProvider>();
                if (cax == null)
                {
                    Console.Error.WriteLine("CaxProvider 不可用，请确认已安装 Openness 且工程支持 CAx 导出。");
                    return 3;
                }

                FileInfo amlFile = new FileInfo(Path.GetFullPath(outAml));
                if (amlFile.Directory != null && !amlFile.Directory.Exists)
                    amlFile.Directory.Create();

                TransferResult result;
                if (!string.IsNullOrWhiteSpace(deviceName))
                {
                    Device device = project.Devices.Find(deviceName);
                    if (device == null)
                    {
                        Console.Error.WriteLine("未找到设备/站: " + deviceName);
                        Console.Error.WriteLine("可用 Devices:");
                        foreach (Device d in project.Devices)
                            Console.Error.WriteLine("  - " + d.Name);
                        return 4;
                    }
                    Console.WriteLine("导出设备: " + device.Name);
                    result = cax.Export(device, amlFile);
                }
                else
                {
                    Console.WriteLine("导出整个工程硬件…");
                    result = cax.Export(project, amlFile);
                }

                Console.WriteLine("结果: " + result.State + "  errors=" + result.ErrorCount + "  warnings=" + result.WarningCount);
                PrintMessages(result.Messages, 0);
                if (result.ErrorCount > 0)
                    return 5;

                Console.WriteLine("已写出: " + amlFile.FullName);
                Console.WriteLine("下一步: python scripts/aml_to_cabinet.py \"" + amlFile.FullName + "\" -o configs\\柜名.json");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(ex.GetType().Name + ": " + ex.Message);
                Console.Error.WriteLine(ex);
                return 1;
            }
        }

        private static TiaPortal AttachOrStart(bool preferAttach)
        {
            if (preferAttach)
            {
                foreach (TiaPortalProcess proc in TiaPortal.GetProcesses())
                {
                    try
                    {
                        Console.WriteLine("附加到已运行的 TIA Portal (PID " + proc.Id + ")…");
                        return proc.Attach();
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine("附加失败: " + ex.Message);
                    }
                }
            }
            Console.WriteLine("启动新的 TIA Portal (WithoutUserInterface)…");
            return new TiaPortal(TiaPortalMode.WithoutUserInterface);
        }

        private static Project OpenOrGetProject(TiaPortal tia, string projectPath)
        {
            if (tia.Projects.Count > 0)
                return tia.Projects[0];

            if (string.IsNullOrWhiteSpace(projectPath))
                return null;

            FileInfo fi = new FileInfo(projectPath);
            if (!fi.Exists)
                throw new FileNotFoundException("工程文件不存在", projectPath);

            Console.WriteLine("打开工程: " + fi.FullName);
            return tia.Projects.Open(fi);
        }

        private static void PrintMessages(TransferResultMessageComposition messages, int depth)
        {
            if (messages == null) return;
            string indent = new string(' ', depth * 2);
            foreach (TransferResultMessage m in messages)
            {
                Console.WriteLine(indent + m.State + " " + m.Message);
                PrintMessages(m.Messages, depth + 1);
            }
        }

        private static void PrintHelp()
        {
            Console.WriteLine(@"CheckPLC TIA Openness CAx Export (V20)

用法:
  CheckPlc.TiaExport.exe [--project path.ap20] [--out export.aml] [--device 站名] [--new]

选项:
  --project, -p   工程 .ap20 路径（Portal 未打开工程时需要）
  --out, -o       输出 AML 路径（默认 .\export.aml）
  --device, -d    只导出指定站/设备名（默认导出整个工程）
  --new           强制启动新 Portal，不附加已运行实例
  --help, -h      显示帮助
");
        }
    }
}
