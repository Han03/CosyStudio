import os
import psutil
import json
from datetime import datetime

class ResourceMonitor:
    def __init__(self):
        self.resource_history = []
        self.max_history = 100
        self.warning_thresholds = {
            'cpu_percent': 80,
            'memory_percent': 85,
            'disk_percent': 95,
            'gpu_memory_percent': 85
        }
    
    def get_system_resources(self):
        """获取系统资源使用情况"""
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        resources = {
            'timestamp': datetime.now().isoformat(),
            'cpu': {
                'percent': cpu_percent,
                'cores': psutil.cpu_count(logical=True),
                'warning': cpu_percent > self.warning_thresholds['cpu_percent']
            },
            'memory': {
                'total': self._format_bytes(memory.total),
                'available': self._format_bytes(memory.available),
                'used': self._format_bytes(memory.used),
                'percent': memory.percent,
                'warning': memory.percent > self.warning_thresholds['memory_percent']
            },
            'disk': {
                'total': self._format_bytes(disk.total),
                'used': self._format_bytes(disk.used),
                'free': self._format_bytes(disk.free),
                'percent': disk.percent,
                'warning': disk.percent > self.warning_thresholds['disk_percent']
            },
            'process': {
                'pid': os.getpid(),
                'memory_usage': self._format_bytes(psutil.Process(os.getpid()).memory_info().rss),
                'memory_percent': psutil.Process(os.getpid()).memory_percent()
            },
            'gpu': self._get_gpu_info()
        }
        
        return resources
    
    def _get_gpu_info(self):
        """获取GPU信息，增加CUDA占用检查"""
        try:
            import torch
            
            if not torch.cuda.is_available():
                return {'available': False, 'message': 'CUDA not available', 'cuda_available': False}
            
            device_name = torch.cuda.get_device_name(0)
            total_memory = torch.cuda.get_device_properties(0).total_memory
            allocated_memory = torch.cuda.memory_allocated(0)
            reserved_memory = torch.cuda.memory_reserved(0)
            memory_free = reserved_memory - allocated_memory
            
            gpu_info = {
                'available': True,
                'name': device_name,
                'memory_total': self._format_bytes(total_memory),
                'memory_used': self._format_bytes(allocated_memory),
                'memory_free': self._format_bytes(memory_free),
                'memory_percent': (allocated_memory / total_memory) * 100,
                'cuda_available': True,
                'cuda_used_by_other_processes': False,
                'other_processes': [],
                'warning': False
            }
            
            gpu_info['warning'] = gpu_info['memory_percent'] > self.warning_thresholds['gpu_memory_percent']
            
            try:
                import subprocess
                result = subprocess.run(
                    ['nvidia-smi', '--query-compute-apps=pid,name,used_gpu_memory', '--format=csv,noheader'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    current_pid = os.getpid()
                    other_processes = []
                    
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            parts = line.split(',')
                            if len(parts) >= 3:
                                try:
                                    pid = int(parts[0].strip())
                                    name = parts[1].strip()
                                    memory_str = parts[2].strip()
                                    
                                    if pid != current_pid:
                                        memory_mb = self._parse_memory(memory_str)
                                        if memory_mb > 100:
                                            other_processes.append({
                                                'pid': pid,
                                                'name': name,
                                                'memory': memory_str,
                                                'memory_mb': memory_mb
                                            })
                                except ValueError:
                                    pass
                    
                    if other_processes:
                        gpu_info['cuda_used_by_other_processes'] = True
                        gpu_info['other_processes'] = other_processes
                        gpu_info['warning'] = True
                
            except Exception as e:
                gpu_info['nvidia_smi_error'] = str(e)
            
            return gpu_info
            
        except Exception as e:
            return {'available': False, 'message': f'GPU detection failed: {str(e)}', 'cuda_available': False}
    
    def _format_bytes(self, bytes_val):
        """格式化字节数为可读格式"""
        if bytes_val == 0:
            return '0 B'
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        while bytes_val >= 1024 and i < len(units) - 1:
            bytes_val /= 1024
            i += 1
        return f'{bytes_val:.2f} {units[i]}'
    
    def _parse_memory(self, memory_str):
        """解析内存字符串为MB"""
        try:
            memory_str = memory_str.strip().upper()
            if 'GB' in memory_str:
                return float(memory_str.replace('GB', '').strip()) * 1024
            elif 'MB' in memory_str:
                return float(memory_str.replace('MB', '').strip())
            elif 'KB' in memory_str:
                return float(memory_str.replace('KB', '').strip()) / 1024
            elif 'B' in memory_str:
                return float(memory_str.replace('B', '').strip()) / 1024 / 1024
            else:
                return float(memory_str)
        except:
            return 0
    
    def check_resource_health(self):
        """检查资源是否健康"""
        resources = self.get_system_resources()
        issues = []
        
        if resources['cpu']['warning']:
            issues.append(f"CPU占用过高: {resources['cpu']['percent']}%")
        
        if resources['memory']['warning']:
            issues.append(f"内存占用过高: {resources['memory']['percent']}%")
        
        if resources['disk']['warning']:
            issues.append(f"磁盘空间不足: {resources['disk']['percent']}%")
        
        if resources['gpu']['available']:
            if resources['gpu']['memory_percent'] > self.warning_thresholds['gpu_memory_percent']:
                issues.append(f"GPU显存占用过高: {resources['gpu']['memory_percent']:.2f}%")
            if resources['gpu'].get('cuda_used_by_other_processes', False):
                other_processes = resources['gpu'].get('other_processes', [])
                process_names = ', '.join([p['name'] for p in other_processes])
                issues.append(f"CUDA被其他进程占用: {process_names}")
        
        return {
            'healthy': len(issues) == 0,
            'issues': issues,
            'resources': resources
        }
    
    def record_resources(self):
        """记录资源状态"""
        resources = self.get_system_resources()
        self.resource_history.append(resources)
        if len(self.resource_history) > self.max_history:
            self.resource_history = self.resource_history[-self.max_history:]
        return resources
    
    def get_history(self):
        """获取资源历史记录"""
        return self.resource_history
    
    def get_summary(self):
        """获取资源摘要"""
        resources = self.get_system_resources()
        return {
            'cpu_percent': resources['cpu']['percent'],
            'memory_percent': resources['memory']['percent'],
            'disk_percent': resources['disk']['percent'],
            'gpu_available': resources['gpu']['available'],
            'gpu_memory_percent': resources['gpu']['memory_percent'] if resources['gpu']['available'] else 0,
            'process_memory': resources['process']['memory_usage'],
            'timestamp': resources['timestamp']
        }

resource_monitor = ResourceMonitor()