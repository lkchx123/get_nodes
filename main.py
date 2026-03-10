import requests
import re
import yaml
import datetime
import urllib3
import os

# 禁用不安全的请求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


github_urls = [
    "https://github.com/abshare/abshare.github.io/blob/main/README.md",
    "https://github.com/mkshare3/mkshare3.github.io/blob/main/README.md",
    "https://github.com/toshare5/toshare5.github.io/blob/main/README.md",
    "https://github.com/abshare3/abshare3.github.io/blob/main/README.md",
    "https://github.com/tolinkshare2/tolinkshare2.github.io/blob/main/README.md",
    "https://github.com/mksshare/mksshare.github.io/blob/main/README.md"
]

CLASH_USER_AGENT = "clash-verge/v2.4.4"
TEMPLATE_FILE = "template.yaml"
OUTPUT_FILE = "merged_config.yaml"
CACHE_FILE = "cache.yaml"


def get_raw_url(github_url):
    """
    将 GitHub blob URL 转换为 raw URL，方便下载。
    （注：为了在大陆地区访问，可以切换为 gh.llkk.cc 等加速服务）
    """
    # return "https://gh.llkk.cc/" + github_url
    return github_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")


def get_subscription_link(github_url):
    """从 GitHub README 中提取 Clash 订阅链接。"""
    raw_url = get_raw_url(github_url)
    print(f"-> 尝试从 {raw_url} 获取订阅链接...")
    try:
        response = requests.get(raw_url, timeout=10, verify=False)
        response.raise_for_status()
        # 使用正则表达式匹配“Clash订阅链接”后的第一个 http/https 链接，re.S 标志让 '.' 匹配包括换行符在内的所有字符
        match = re.search(r'Clash订阅链接.*?((?:https?|http)://\S+)', response.text, re.S)
        if match:
            link = match.group(1).strip()
            print(f"   ✓ 成功找到链接: {link}")
            return link
        else:
            print(f"   ✗ 在 {raw_url} 中未找到 Clash 订阅链接。")
            return None
    except requests.exceptions.RequestException as e:
        print(f"   ✗ 请求 {raw_url} 失败: {e}")
        return None
    

def get_current_ip():
    """获取当前网络的出口 IP 地址。"""
    print("--- 检查网络连接 ---")
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        print(f"当前访问 IP: {response.json().get('ip')}")
    except requests.exceptions.RequestException as e:
        print(f"无法获取当前 IP，网络可能存在问题: {e}")
    print("-" * 31)


def download_and_extract_proxies(link):
    """下载并解析 Clash 配置文件，提取并过滤代理节点列表。"""
    try:
        headers = {'User-Agent': CLASH_USER_AGENT}
        response = requests.get(link, headers=headers, timeout=20, verify=False)
        response.raise_for_status()
        config_data = yaml.safe_load(response.text)
        if not config_data or 'proxies' not in config_data:
            print(f"   ✗ 警告: YAML 解析为空或缺少 'proxies' 部分, 链接: {link}")
            return None
        
        proxies = config_data.get('proxies', [])
        filtered_proxies = [
            p for p in proxies
            if isinstance(p, dict) and 'name' in p and "剩余流量" not in p['name'] and "套餐到期" not in p['name']
        ]
        return filtered_proxies
        
    except (requests.exceptions.RequestException, yaml.YAMLError) as e:
        print(f"   ✗ 下载或解析 {link} 失败: {e}")
        return None

def load_cache():
    """优先从远程 cache.yaml 加载数据，失败则回退本地缓存。"""
    remote_url = "https://raw.githubusercontent.com/lkchx123/get_nodes/main/cache.yaml"
    try:
        print(f"-> 尝试从远程加载缓存: {remote_url}")
        response = requests.get(remote_url, timeout=10)
        response.raise_for_status()
        print(f"✓ 成功加载远程缓存文件")
        return yaml.safe_load(response.text) or {}
    except Exception as e:
        print(f"✗ 警告: 加载远程缓存失败: {e}")
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    print(f"✓ 成功加载本地缓存文件 '{CACHE_FILE}'")
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"✗ 警告: 加载本地缓存文件 '{CACHE_FILE}' 失败: {e}")
    return {}

def save_cache(cache_data):
    """将数据保存到缓存文件。"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(cache_data, f, sort_keys=False, allow_unicode=True)
        print(f"✓ 成功更新缓存文件 '{CACHE_FILE}'")
    except Exception as e:
        print(f"✗ 警告: 保存缓存文件 '{CACHE_FILE}' 失败: {e}")


def merge_configs():
    """
    主函数：加载模板，下载并追加所有新代理节点，然后更新模板中的代理组。
    """
    get_current_ip()

    # 1. 加载本地模板文件
    try:
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            base_config = yaml.safe_load(f)
        print(f"\n✓ 成功加载模板文件 '{TEMPLATE_FILE}'")
    except Exception as e:
        print(f"\n✗ 错误: 加载或解析模板文件 '{TEMPLATE_FILE}' 失败: {e}")
        return

    # 加载缓存
    cache = load_cache()

    print("\n--- 开始获取并合并 Clash 订阅 ---")

    all_new_proxies = []
    success_count = 0

    # 2. 遍历URL，获取所有代理节点
    for url in github_urls:
        author_match = re.search(r'github\.com/([a-zA-Z0-9_-]+)/', url)
        author = author_match.group(1) if author_match else "unknown"

        # 从 GitHub README 中获取订阅链接
        current_clash_link = get_subscription_link(url)

        proxies_from_sub = None

        # 3. 检查缓存
        if url in cache and cache[url].get('clash_link') == current_clash_link:
            # 找到缓存，且clash链接没变
            print(f"   ✓ 订阅链接未变，使用缓存。")
            proxies_from_sub = cache[url].get('proxies')

        # 4. 如果没有命中缓存或者缓存节点无效，则重新下载
        if not proxies_from_sub:
            if not current_clash_link:
                print("-" * 31)
                # 获取订阅链接失败，从缓存中删除此项，防止残留
                if url in cache:
                    print(f"   ✗ 获取新链接失败，删除旧缓存。")
                    del cache[url]
                continue

            proxies_from_sub = download_and_extract_proxies(current_clash_link)

            if proxies_from_sub:
                # 下载成功，更新缓存
                cache[url] = {
                    'clash_link': current_clash_link,
                    'proxies': proxies_from_sub
                }
            else:
                # 下载失败，从缓存中删除此项，防止残留
                if url in cache:
                    print(f"   ✗ 下载失败，删除旧缓存。")
                    del cache[url]

        if proxies_from_sub:
            for proxy in proxies_from_sub:
                if isinstance(proxy, dict) and 'name' in proxy:
                    new_proxy = proxy.copy()  # 创建一个浅拷贝副本，防止缓存中带author，从而重复添加author
                    new_proxy['name'] = f"{new_proxy['name']} | {author}"
                    all_new_proxies.append(new_proxy)
            print(f"   ✓ 从此订阅中获取了 {len(proxies_from_sub)} 个代理节点。")
            success_count += 1
        print("-" * 31)

    # 保存更新后的缓存
    save_cache(cache)

    if success_count == 0:
        print("\n✗ 所有订阅链接均无法获取")

    # 5. 保留模板原有节点，将新节点追加到后面
    new_proxy_names = [p['name'] for p in all_new_proxies]
    original_proxies = base_config['proxies']
    base_config['proxies'] = original_proxies + all_new_proxies

    # 6. 处理原有的“手动选择”组
    if 'proxy-groups' in base_config:
        for group in base_config['proxy-groups']:
            if group.get('name') == "手动选择":
                group['proxies'].extend(new_proxy_names)
                break

    # 7. 地区分组
    regions = {}
    for p in all_new_proxies:
        match = re.search(r'^[^\s]+', p['name'])
        region_name = match.group() if match else "其他地区"
        if region_name not in regions:
            regions[region_name] = []
        regions[region_name].append(p['name'])

    region_group_names = []
    for r_name, p_list in regions.items():
        base_config['proxy-groups'].append({
            'name': r_name,
            'type': 'fallback',
            'url': 'https://cp.cloudflare.com/generate_204',
            'interval': 30,
            'proxies': p_list
        })
        region_group_names.append(r_name)

    for group in base_config['proxy-groups']:
        if group.get('name') == "地区选择":
            group['proxies'] = region_group_names
            break

    # 8. 写入最终的合并配置
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    timestamp = timestamp.translate(str.maketrans('0123456789', '𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵'))
    yaml_content = yaml.dump(base_config, sort_keys=False, allow_unicode=True)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"# ⏰配置合并于 {timestamp}\n")
        f.write(yaml_content.replace("测试节点", f"⏰⏰⏰配置合并于 {timestamp}"))

    print("\n--- 合并完成！ ---")
    print(f"已从{success_count}个订阅链接中成功合并了 {len(new_proxy_names)} 个节点。")
    print(f"最终配置文件 '{OUTPUT_FILE}' 已生成。")


if __name__ == "__main__":
    merge_configs()









