#!/usr/bin/env python3
import sys
import yaml
import copy

def load_yaml(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def load_env_file(filepath):
    env_vars = {}
    try:
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        full_path = os.path.join(base_dir, filepath)
        with open(full_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    env_vars[k.strip()] = v.strip().strip("'").strip('"')
    except Exception as e:
        print(f"Warning: Could not read env file {filepath}: {e}")
    return env_vars

def generate_compose(spec):
    compose = {"services": {}}
    
    if "compose" in spec and "volumes" in spec["compose"]:
        compose["volumes"] = spec["compose"]["volumes"]
    
    service_profiles = {}
    if "global" in spec and "profiles" in spec["global"]:
        for profile, services in spec["global"]["profiles"].items():
            for s in services:
                if s not in service_profiles:
                    service_profiles[s] = []
                service_profiles[s].append(profile)

    for s_name, s_def in spec.get("services", {}).items():
        c_def = {}
        
        if "targets" in s_def and "dev" in s_def["targets"]:
            dev = s_def["targets"]["dev"]
            if "build" in dev:
                c_def["build"] = dev["build"]
                
        # Optional custom image from dev target overrides base
        if "targets" in s_def and "dev" in s_def["targets"] and "image" in s_def["targets"]["dev"]:
            c_def["image"] = s_def["targets"]["dev"]["image"]
        elif "image" in s_def:
            c_def["image"] = s_def["image"]
            
        c_def["container_name"] = s_name

        if s_name in service_profiles:
            c_def["profiles"] = service_profiles[s_name]

        if "ports" in s_def:
            c_def["ports"] = s_def["ports"]
            
        if "envFile" in s_def:
            c_def["env_file"] = s_def["envFile"]
            
        if "env" in s_def:
            c_def["environment"] = s_def["env"]
            
        if "volumes" in s_def:
            c_def["volumes"] = s_def["volumes"]
            
        if "memory" in s_def:
            c_def["mem_limit"] = s_def["memory"]
            
        if "healthcheck" in s_def:
            c_def["healthcheck"] = copy.deepcopy(s_def["healthcheck"])
            if "startPeriod" in c_def["healthcheck"]:
                c_def["healthcheck"]["start_period"] = c_def["healthcheck"].pop("startPeriod")
                
        if "command" in s_def:
            c_def["command"] = s_def["command"]
            
        if "restart" in s_def:
            c_def["restart"] = s_def["restart"]
            
        if "waitsFor" in s_def:
            c_def["depends_on"] = {}
            for target, condition in s_def["waitsFor"].items():
                c_def["depends_on"][target] = {"condition": condition}

        if "ulimits" in s_def:
            c_def["ulimits"] = s_def["ulimits"]

        compose["services"][s_name] = c_def

    return compose

def generate_values(spec):
    values = {}
    if "global" in spec:
        values["global"] = copy.deepcopy(spec["global"])
        
    for s_name, s_def in spec.get("services", {}).items():
        v_def = {}
        
        if "targets" in s_def and "helm" in s_def["targets"]:
            helm_def = s_def["targets"]["helm"]
            if "replicas" in helm_def:
                v_def["replicas"] = helm_def["replicas"]
            if "ingress" in helm_def:
                v_def["ingress"] = helm_def["ingress"]
                
        if "image" in s_def:
            v_def["image"] = s_def["image"]
            
        if "memory" in s_def:
            mem = s_def["memory"].replace('g', 'Gi')
            v_def["resources"] = {
                "limits": {"memory": mem},
                "requests": {"memory": mem}
            }
            
        if "envFile" in s_def:
            for ef in s_def["envFile"]:
                loaded_env = load_env_file(ef)
                if "env" not in v_def:
                    v_def["env"] = {}
                v_def["env"].update(loaded_env)
                
        if "env" in s_def:
            if "env" not in v_def:
                v_def["env"] = {}
            v_def["env"].update(s_def["env"])
            
        if "ports" in s_def:
            v_def["ports"] = s_def["ports"]
            
        if "restart" in s_def:
            v_def["restart"] = s_def["restart"]
            
        if "command" in s_def:
            v_def["command"] = s_def["command"]
            
        if "volumes" in s_def:
            import os
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[1])))
            v_def["volumes"] = []
            for vol in s_def["volumes"]:
                parts = vol.split(':')
                src = parts[0]
                dst = parts[1]
                read_only = len(parts) > 2 and parts[2] == 'ro'
                vol_obj = {
                    "mountPath": dst,
                    "readOnly": read_only
                }
                if src.startswith('.'):
                    rel_path = src[2:] if src.startswith('./') else src
                    abs_path = os.path.abspath(os.path.join(repo_root, rel_path))
                    vol_obj["hostPath"] = rel_path
                    vol_obj["hostPathType"] = "File" if os.path.isfile(abs_path) else "DirectoryOrCreate"
                else:
                    vol_obj["type"] = "emptyDir"
                    vol_obj["name"] = src
                v_def["volumes"].append(vol_obj)

        safe_name = s_name.replace('-', '_')
        values[safe_name] = v_def
        
    return values

def main():
    if len(sys.argv) < 3:
        print("Usage: generate.py <spec.yaml> <output-compose.yml> [output-values.yaml]")
        sys.exit(1)
        
    spec_path = sys.argv[1]
    out_path = sys.argv[2]
    out_values_path = sys.argv[3] if len(sys.argv) > 3 else None
    
    spec = load_yaml(spec_path)
    compose = generate_compose(spec)
    
    class MyDumper(yaml.Dumper):
        def increase_indent(self, flow=False, indentless=False):
            return super(MyDumper, self).increase_indent(flow, False)

    with open(out_path, 'w') as f:
        yaml.dump(compose, f, Dumper=MyDumper, default_flow_style=False, sort_keys=False)

    if out_values_path:
        values = generate_values(spec)
        with open(out_values_path, 'w') as f:
            yaml.dump(values, f, Dumper=MyDumper, default_flow_style=False, sort_keys=False)

if __name__ == "__main__":
    main()
