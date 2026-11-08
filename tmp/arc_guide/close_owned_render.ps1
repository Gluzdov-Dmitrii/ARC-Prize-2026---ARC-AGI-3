param(
    [Parameter(Mandatory=$true)][string]$DocumentPath,
    [Parameter(Mandatory=$true)][int]$ExpectedProcessId
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
public static class RenderOwnedDocument {
    [DllImport("ole32.dll")] static extern int GetRunningObjectTable(int reserved, out IRunningObjectTable rot);
    [DllImport("ole32.dll")] static extern int CreateBindCtx(int reserved, out IBindCtx context);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
    delegate bool EnumWindowCallback(IntPtr window, IntPtr argument);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowCallback callback, IntPtr argument);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr window, EnumWindowCallback callback, IntPtr argument);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr window, StringBuilder name, int max);
    [DllImport("oleacc.dll")] static extern int AccessibleObjectFromWindow(IntPtr window, uint id, ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out object result);
    public static object NativeWindowForProcess(uint wantedPid) {
        object found=null;
        EnumWindows(delegate(IntPtr top, IntPtr ignored) {
            uint pid; GetWindowThreadProcessId(top,out pid);
            if (pid!=wantedPid) return true;
            EnumChildWindows(top,delegate(IntPtr child, IntPtr ignoredChild) {
                StringBuilder className=new StringBuilder(256); GetClassName(child,className,256);
                if (className.ToString()!="_WwG") return true;
                Guid iid=new Guid("00020400-0000-0000-C000-000000000046");
                object value;
                if (AccessibleObjectFromWindow(child,0xFFFFFFF0,ref iid,out value)==0) found=value;
                return found==null;
            },IntPtr.Zero);
            return found==null;
        },IntPtr.Zero);
        return found;
    }
    public static uint ProcessForWindow(int handle) {
        uint pid; GetWindowThreadProcessId(new IntPtr(handle), out pid); return pid;
    }
    public static object FindExactDocument(string path) {
        IRunningObjectTable rot; IBindCtx context; IEnumMoniker entries;
        Marshal.ThrowExceptionForHR(GetRunningObjectTable(0,out rot));
        Marshal.ThrowExceptionForHR(CreateBindCtx(0,out context));
        rot.EnumRunning(out entries);
        IMoniker[] entry = new IMoniker[1];
        try {
            while (entries.Next(1,entry,IntPtr.Zero)==0) {
                try {
                    string name;
                    try { entry[0].GetDisplayName(context,null,out name); } catch { continue; }
                    if (String.Equals(name,path,StringComparison.OrdinalIgnoreCase)) {
                        object value; rot.GetObject(entry[0],out value); return value;
                    }
                } finally { Marshal.ReleaseComObject(entry[0]); }
            }
            return null;
        } finally {
            Marshal.ReleaseComObject(entries); Marshal.ReleaseComObject(context); Marshal.ReleaseComObject(rot);
        }
    }
}
'@
$exactPath=[IO.Path]::GetFullPath($DocumentPath)
$ownedDocument=$null
$ownedApplication=$null
$nativeVerifiedProcessId=0
if ($null -eq $ownedDocument) {
    $nativeWindow=[RenderOwnedDocument]::NativeWindowForProcess($ExpectedProcessId)
    if ($null -eq $nativeWindow) {
        Write-Output 'The owned Word document could not be recovered; nothing closed.'
        exit 2
    }
    $ownedApplication=$nativeWindow.Application
    $nativeVerifiedProcessId=$ExpectedProcessId
    foreach ($candidateDocument in $ownedApplication.Documents) {
        if ($candidateDocument.FullName -eq $exactPath) { $ownedDocument=$candidateDocument; break }
    }
    if ($null -eq $ownedDocument) { throw 'Owned Word instance has no document at the exact expected path.' }
}
try {
    if ($ownedDocument.FullName -ne $exactPath) { throw 'Document path does not match.' }
    $ownedApplication=$ownedDocument.Application
    $actualProcessId=$nativeVerifiedProcessId
    if ($actualProcessId -eq 0) {
        $actualProcessId=[RenderOwnedDocument]::ProcessForWindow($ownedApplication.ActiveWindow.Hwnd)
    }
    if ($actualProcessId -ne $ExpectedProcessId) { throw ('Instance PID mismatch: '+$actualProcessId) }
    if ($ownedApplication.Visible) { throw 'Refusing to close a visible instance.' }
    if (!$ownedDocument.ReadOnly) { throw 'Refusing to close a document that is not read only.' }
    $ownedDocument.Saved=$true
    $ownedDocument.Close()
    if ($ownedApplication.Documents.Count -eq 0) {
        $ownedApplication.Quit()
    }
    Write-Output ('Closed the render document belonging to PID '+$actualProcessId)
}
finally {
    if ($null -ne $ownedDocument) { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($ownedDocument) | Out-Null }
    if ($null -ne $ownedApplication) { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($ownedApplication) | Out-Null }
}
