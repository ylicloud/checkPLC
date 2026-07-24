using System;
using System.IO;
using Siemens.Engineering;
using Siemens.Engineering.Cax;
using Siemens.Engineering.HW;

namespace CheckPlc.TiaExport
{
    internal static class CaxExporter
    {
        internal static int Run(string projectPath, string outAml, string deviceName, bool attach)
        {
            try
            {
                TiaPortal tia = AttachOrStart(attach);
                Project project = OpenOrGetProject(tia, projectPath);
                if (project == null)
                {
                    Console.Error.WriteLine("未找到已打开工程。请先在 Portal 中打开工程，或使用 --project 指定 .ap20/.ap21。");
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
                Console.Error.WriteLine(Program.SafeMessage(ex));
                Exception cur = ex;
                int depth = 0;
                while (cur != null && depth < 8)
                {
                    try
                    {
                        Console.Error.WriteLine("  [" + depth + "] " + cur.GetType().FullName + ": " + cur.Message);
                        if (!string.IsNullOrEmpty(cur.StackTrace))
                            Console.Error.WriteLine(cur.StackTrace);
                    }
                    catch
                    {
                        Console.Error.WriteLine("  [" + depth + "] (该层异常无法打印)");
                    }
                    cur = cur.InnerException;
                    depth++;
                }
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
    }
}
