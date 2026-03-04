import os
import shutil
import zipfile
import subprocess
from pathlib import Path
os.environ['PYTHONIOENCODING'] = 'utf-8'
def main(target_folder=None):
    # 设置桌面路径
    desktop = Path.home() / "Desktop"
    
    # 设置目标文件夹
    if target_folder is None:
        target_folder = desktop / "PackageAllLogs"
    else:
        target_folder = target_folder / "PackageAllLogs"
    # 设置 localappdata 路径
    localappdata = Path(os.environ.get('LOCALAPPDATA', ''))
    userprofile = Path.home()
    
    # 如果目标文件夹已存在，则删除它
    if target_folder.exists():
        print(f"Deleting existing folder {target_folder}...")
        shutil.rmtree(target_folder, ignore_errors=True)
    
    # 如果已存在压缩包，则删除它
    zip_file = target_folder.parent / "PackageAllLogs.zip"
    if zip_file.exists():
        print(f"Deleting existing zip file PackageAllLogs.zip...")
        zip_file.unlink()
    
    # 创建目标文件夹
    print(f"Creating new folder {target_folder}...")
    target_folder.mkdir(parents=True, exist_ok=True)
    
    # 定义需要拷贝的源路径和目标路径
    copy_tasks = [
        {
            'source': localappdata / "quantum_core",
            'dest': target_folder / "pod7_10_28",
            'desc': "quantum_core.log"
        },
        {
            'source': localappdata / "mcp_mgmt_service",
            'dest': target_folder / "mcp_mgmt_service",
            'desc': "mcp_mgmt_service.log"
        },
        {
            'source': localappdata / "mgmt_sc_mcp_server",
            'dest': target_folder / "mgmt_sc_mcp_server",
            'desc': "mgmt_sc_mcp_server.log"
        },
        {
            'source': localappdata / "Lenovo" / "Lenovo Qira" / "Log",
            'dest': target_folder / "pod1_20_QiraApp",
            'desc': "log folder files"
        },
        {
            'source': Path("C:/Program Files/Lenovo/Lenovo Qira/Lenovo.McpMgmtService/mcp/LocalAgentMCP/fileSearch/logs"),
            'dest': target_folder / "pod1",
            'desc': "LocalAgentMCP fileSearch logs"
        },
        {
            'source': localappdata / "Lenovo" / "QuantumAI" / "Log",
            'dest': target_folder / "pod3_4_5_qtservice",
            'desc': "QuantumAI log folder files"
        },
        {
            'source': Path("C:/Program Files/Lenovo/Lenovo Qira/Lenovo.McpMgmtService/mcp/LocalAgentMCP/logs"),
            'dest': target_folder / "pod1",
            'desc': "LocalAgentMCP log folder files"
        },
        {
            'source': userprofile / "modelServiceLog",
            'dest': target_folder / "ModelService",
            'desc': "ModelService log file"
        },
        {
            'source': Path("C:/ProgramData/lenovo/modelmgr/logs"),
            'dest': target_folder / "pod21",
            'desc': "createzone log file"
        }
    ]
    
    # 执行拷贝任务
    for task in copy_tasks:
        print(f"Copying {task['desc']}...")
        copy_directory(task['source'], task['dest'])
    
    # 压缩文件夹为 zip 文件
    print("Compressing the PackageAllLogs folder...")
    create_zip(target_folder, zip_file)
    
    # # 在资源管理器中选中压缩文件
    # print("Opening file location in explorer...")
    # try:
    #     subprocess.run(['explorer.exe', '/select,', str(zip_file)], check=False)
    # except Exception as e:
    #     print(f"Could not open explorer: {e}")
    
    # 删除 PackageAllLogs 文件夹
    print("Deleting the PackageAllLogs folder...")
    shutil.rmtree(target_folder, ignore_errors=True)
    
    # print("Backup, compression, and cleanup complete!")
    # input("Press Enter to exit...")


def copy_directory(source, dest):
    """
    拷贝目录或文件，如果源不存在则跳过
    """
    try:
        if not source.exists():
            print(f"  Source not found: {source}, skipping...")
            return
        
        # 确保目标目录存在
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        if source.is_file():
            # 如果是文件，直接拷贝
            shutil.copy2(source, dest)
        else:
            # 如果是目录，拷贝整个目录树
            if dest.exists():
                # 如果目标已存在，合并内容
                shutil.copytree(source, dest, dirs_exist_ok=True)
            else:
                shutil.copytree(source, dest)
        
        print(f"  Successfully copied from {source} to {dest}")
    except PermissionError as e:
        print(f"  Permission denied: {e}")
    except Exception as e:
        print(f"  Error copying {source}: {e}")


def create_zip(source_folder, zip_path):
    """
    创建 zip 压缩文件
    """
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_folder):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(source_folder.parent)
                    zipf.write(file_path, arcname)
        print(f"  Successfully created zip file: {zip_path}")
    except Exception as e:
        print(f"  Error creating zip file: {e}")


if __name__ == "__main__":
    CURRENT_DIR = Path(__file__).parent
    target_folder = CURRENT_DIR / "PackageAllLogs"  # 或者指定一个路径，例如 Path.home() / "Desktop" / "MyLogs"
    main(target_folder)