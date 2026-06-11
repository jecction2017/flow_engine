from __future__ import annotations

import json
import math
import re
from urllib.parse import urlparse

import pandas

scripts = {
  "query": {
    "bool": {
      "must": [
        {
          "range": {
            "last_update_time": {
              "gte": "now-2h",
              "lte": "now"
            }
          }
        },
        {
          "match": {
            "subject_account": "h30027363"
          }
        }
      ]
    }
  }
}
jalor_url_patterns = ["/security/userPermission/addPermissions2User/"
    , "/security/userPermission/updateUserPermissions/"]


def append_jalor_url_desc(alarm: dict, subject_type: str, abnormal_desc: list):
    if not alarm["object_url"] or not alarm["indicator_evidence"]:
        return
    for desc in abnormal_desc:
        if "近2小时内有成功访问jalor高价值接口" in desc:
            return
    subject = alarm[subject_type]
    object_url = alarm.get("object_url", "")
    if isinstance(object_url, list):
        object_url = ",".join(object_url)
    indicator_evidence = alarm["indicator_evidence"]
    status = indicator_evidence.get("status", "")
    is_jalor_url = False
    for pattern in jalor_url_patterns:
        is_match = True
        urls = pattern.split(',')
        for url in urls:
            if url.lower() not in object_url.lower():
                is_match = False
                break
        if is_match:
            is_jalor_url = True
            break
    if is_jalor_url and (status.startswith('2') or status == '500'):
        subject_type_str = "IP" if subject_type == "subject_ip" else "账号"
        abnormal_desc.append(
            f"该{subject_type_str}({subject})近2小时内有成功访问jalor高价值接口（比如： {object_url}）"
        )

def duplicate_domain_crawler(urls: dict, object_url_pattern: list = None):
    # 取前n个url 要保证域名多样性
    head, tail = list(), list()
    df = pandas.DataFrame()
    df["url"] = list(urls.keys())
    df["count"] = list(urls.values())
    df["domain"] = df["url"].apply(lambda x: x.split("/")[2])
    df["is_contains_page"] = df["url"].apply(lambda x: int("page" in x))
    df["is_contains_num"] = df["url"].apply(lambda x: int("{num}" in x))
    if object_url_pattern:
        alarm_url = df[df["url"].isin(object_url_pattern)]["url"].tolist()
        head.extend(alarm_url)
        df = df[~df["url"].isin(object_url_pattern)]
    df.sort_values(by=["is_contains_page", "is_contains_num", "count"], ascending=[False, False, False],
                   inplace=True)
    for domain in df["domain"].drop_duplicates():
        tmp_df = df[df["domain"] == domain]
        tmp_url = tmp_df["url"].tolist()
        head.append(tmp_url[0])
        tail.extend(tmp_url[1:])
    head.extend(tail)
    return head


def duplicate_domain_count(urls: list, url_access_count: dict, object_url_pattern: list = None) -> list:
    # 取前n个url 要保证域名多样性
    head, tail = list(), list()
    df = pandas.DataFrame()
    df["url"] = urls
    df["domain"] = df["url"].apply(lambda x: x.split("/")[2])
    df["count"] = df["url"].apply(lambda x: url_access_count.get(x, 0))
    if object_url_pattern:
        alarm_url = df[df["url"].isin(object_url_pattern)]["url"].tolist()
        head.extend(alarm_url)
        df = df[~df["url"].isin(object_url_pattern)]
    df.sort_values(by="count", ascending=False, inplace=True)  # 先按count 排名, 优先取访问次数多的域名
    for domain in df["domain"].drop_duplicates().tolist():
        tmp_df = df[df["domain"] == domain]
        tmp_url = tmp_df["url"].tolist()
        head.append(tmp_url[0])
        tail.extend(tmp_url[1:])
    head.extend(tail)
    return head

class URLClassifier:
    def __init__(self, rules):
        # 提前编译所有正则表达式，提升性能
        self.compiled_rules = {
            category: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for category, patterns in rules.items()
        }

    def classify(self, url):
        """
        判断 URL 属于哪个分类，返回分类名称。如果不匹配则返回 None。
        """
        for category, patterns in self.compiled_rules.items():
            for pattern in patterns:
                if pattern.search(url):
                    return category
        return None

    def is_match_url(self, url):
        return True if self.classify(url) else False

# 定义规则
rules_config = {
    'media': [
        r'/image/.*(resize|crop|thumb|compress)',
        r'/video/.*(segment|clip|transcode)',
        r'/pdf/.*(preview|convert|merge)',
    ],
    'streaming': [
        r'/ws/',
        r'/socket\.io/',
        r'/stream/',
        r'/chunk/',
    ],
    'static': [
        r'\.(jpg|jpeg|png|gif|webp|svg|ico|css|js|woff|ttf|eot|mp4|mp3|pdf|zip|gz)$',
        r'/static/',
        r'/media/',
    ],
    'cc': [
        r'onebox\.cc\.com',
        r'clouddrive.*\.cc\.com',
        r'edm.*\.cc\.com',
    ],
}

# --- 使用示例 ---
classifier = URLClassifier(rules_config)

def _is_fake_xff(ip: str) -> bool:
    # 判断是否伪造的x_forwarded_for
    # A类的10.0.0.0/8，B类的172.16.0.0/12，C类的192.168.0.0/16
    if not ip:
        return False
    if ip.startswith("10."):
        return True
    if ip == "1.1.1.1":
        return True
    if ip.startswith("192.168"):
        return True
    if ip.startswith("127."):
        return True
    if ip.startswith("172."):
        return is_private_172(ip)
    return False


def is_private_172(ip: str) -> bool:
    parts = ip.split(".")
    if len(parts) < 2:  # 连第二段都没有
        return False
    try:
        ip2 = int(parts[1])  # 只可能抛 ValueError
    except ValueError:  # 非数字字符、空字符串、前导空格等
        return False
    return ip.startswith("172.") and 16 <= ip2 <= 31

def get_url_latest_7d_resp_size_avg_batch(es: ESClient, es_data, alarm_urls: list[str]) -> dict:
    res = dict()
    url = list(
        set(row["_source"]["url_pattern"] for row in es_data["hits"]["hits"] if row["_source"].get("url_pattern")))
    url = url + alarm_urls
    for i in range(0, len(url), 5000):
        script = {
            "query": {
                "terms": {
                    "url_pattern": url[i: i + 5000]
                }
            },
            "_source": ["url_pattern", "latest_7d_resp_size_avg", "latest_7d_count", "ip_7d_dc", "top_methods",
                        "latest_24h_count", "create_time", "app_id"],
            "size": 1000000
        }
        data = es.search(index="t_url_info", body=script, size=1000000)
        resolve_url_data(data, res)
    return res
def resolve_url_data(data, res):
    for row in data["hits"]["hits"]:
        row = row["_source"]
        ip_7d_dc = float(row.get("ip_7d_dc", 0))
        latest_7d_count = float(row.get("latest_7d_count", 0))
        res[row["url_pattern"]] = {
            "latest_7d_resp_size_avg": float(row.get("latest_7d_resp_size_avg", 0)),
            "top_methods": row.get("top_methods", ""),
            "top_status_codes": row.get("top_status_codes", ""),
            "create_time": row.get("create_time"),
            "ip_7d_dc": ip_7d_dc,
            "latest_24h_count": float(row.get("latest_24h_count", 0)),
            "latest_7d_count": latest_7d_count,
            "baseline": (latest_7d_count / ip_7d_dc) * 0.8 / (24 * 7 * 0.2) * 2 if ip_7d_dc != 0 else 0,
            "app_id": row.get("app_id", "")
        }
        res[row["url_pattern"]]["top_methods"] = [method.split(":")[0] for method in
                                                  res[row["url_pattern"]]["top_methods"].split("\n")][:1]
        res[row["url_pattern"]]["top_status_codes"] = [status.split(":")[0] for status in
                                                       res[row["url_pattern"]]["top_status_codes"].split("\n")][:2]
def select_intranet_dmz_ips(es, data: dict) -> set:
    all_ips = []
    for hit in data["hits"]["hits"]:
        xff_freq_dict_str = hit["_source"].get("xff_freq_dict", '{}')
        xff_freq_dict = json.loads(xff_freq_dict_str)
        ips = list(xff_freq_dict.keys())
        all_ips.extend(ips)
    all_ips = list(set(all_ips))
    resp = query_intranet_ips(es, all_ips)
    return {hit["_source"]["ip"] for hit in resp.get("hits", {}).get("hits", [])
            if "dmz" in hit["_source"].get("network_area", "").lower()}

def extract_domain(url):
    """
    提取 URL 的域名，支持无协议头的情况
    """
    if not url:
        return ""

    # 去除首尾空格
    url = url.strip()

    # 如果没有协议头 (如 //, http://, https://)，urllib 无法正确识别域名
    # 我们临时补齐协议头以便解析
    if not (url.startswith('http://') or url.startswith('https://') or url.startswith('//')):
        url = 'http://' + url

    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc

        # 排除可能包含端口号的情况 (例如 localhost:8080)
        if ':' in domain:
            domain = domain.split(':')[0]

        return domain
    except Exception:
        return ""

EXCLUDED_APPID = "com.cc.all"

def check_multi_url_consistency(url: str, alarm_urls: list[str], url_info_dict: dict[str, dict]) -> bool:
    for a_url in alarm_urls:
        if check_url_consistency(url, a_url, url_info_dict):
            return True
    return False

def check_url_consistency(url1: str, url2: str, url_info_dict: dict[str, dict]) -> bool:
    """
    校验两个URL出处是否一致

    判断逻辑：
    1. URL如果一样，返回True
    2. URL的域名如果一样，返回True
    3. URL的所属appid如果一样则返回True（排除appid等于"com.baidu.app"的情况）

    Args:
        url1: 第一个URL
        url2: 第二个URL
        url_info_dict: 存储URL所属应用信息的字典，格式为 {url: {"appid": xxx, ...}}

    Returns:
        bool: 如果出处一致返回True，否则返回False
    """

    # 规则1: URL完全一样
    if url1 == url2:
        return True

    domain1 = extract_domain(url1)
    domain2 = extract_domain(url2)

    # 规则2: 域名一样
    if domain1 and domain2 and domain1 == domain2:
        return True

    # 规则3: 所属appid一样（排除com.baidu.app）
    info1 = url_info_dict.get(url1, {})
    info2 = url_info_dict.get(url2, {})

    appid1 = info1.get("app_id")
    appid2 = info2.get("app_id")

    if (appid1 and appid2 and
            appid1 == appid2 and
            appid1 != EXCLUDED_APPID):
        return True

    return False

def get_subject_access_url_features(es_data, subject_type: str, url_info: dict, alarm: dict,
                                    intranet_dmz_ips: set) -> list:
    # 获取特征
    abnormal_desc = list()
    url_access_count = dict()  # {"url": count}
    one_url_multiple_status = dict()  # {"主体": {"url": [status1, status2...], "url": [status...]}}
    one_url_multiple_method = dict()  # {"主体": {"url": [方法...], "url": [method...]}}
    fake_xff = dict()  # {"10.68.10.237": {"www.test1.com": ['1.1.1.1'], 'www.test2.com':['127.0.0.1']}}
    ua_type = dict()  # {"主体": {ua1, ua2...}}
    url_max_resp_size = dict()  # {"主体": {"url1": 123, "url2": 456}}
    subject_access_url_count = dict()  # {"主体": {"url1": 访问次数, "url2": 访问次数}}
    access_jalor_url_200 = dict()
    access_external_ai_app = dict()  # 访问外边界ai应用
    subject_type_str = "IP" if subject_type == "subject_ip" else "账号"

    for row in es_data["hits"]["hits"]:
        row = row["_source"]
        if not row.get(subject_type):
            continue
        subject = row[subject_type]
        url = row["url_pattern"]
        for col in ["high_worth_api_type", "attack_hw_target"]:
            if row.get(col):
                if url in url_info:
                    url_info[url][col] = row[col]
                else:
                    url_info[url] = {col: row[col]}
        if row.get("count"):
            if url not in url_access_count:
                url_access_count[url] = int(float(row["count"]))
            else:
                url_access_count[url] += int(float(row["count"]))
        if row.get("count"):
            if subject not in subject_access_url_count:
                subject_access_url_count[subject] = dict()
            if url not in subject_access_url_count[subject]:
                subject_access_url_count[subject][url] = [int(float(row["count"]))]
            else:
                subject_access_url_count[subject][url].append(int(float(row["count"])))
        if row.get("xff_freq_dict") and row.get("is_intranet", "") != "1":
            if subject not in fake_xff:
                fake_xff[subject] = dict()
            for ip in json.loads(row["xff_freq_dict"]):
                if _is_fake_xff(ip) and (ip not in intranet_dmz_ips):
                    if url not in fake_xff[subject]:
                        fake_xff[subject][url] = [ip]
                    else:
                        fake_xff[subject][url].append(ip)
        if row.get("method_freq_dict"):
            if subject not in one_url_multiple_method:
                one_url_multiple_method[subject] = dict()
            for method, count in json.loads(row["method_freq_dict"]).items():
                if url not in one_url_multiple_method[subject]:
                    one_url_multiple_method[subject][url] = [method] * int(float(count))
                else:
                    one_url_multiple_method[subject][url].extend([method] * int(float(count)))
        if row.get("status_freq_dict"):
            if subject not in one_url_multiple_status:
                one_url_multiple_status[subject] = dict()
            for status, count in json.loads(row["status_freq_dict"]).items():
                if url not in one_url_multiple_status:
                    one_url_multiple_status[subject][url] = [status] * int(float(count))
                else:
                    one_url_multiple_status[subject][url].extend([status] * int(float(count)))
        if row.get("http_user_agent_freq_dict"):
            if subject not in ua_type:
                ua_type[subject] = set()
            for ua in json.loads(row["http_user_agent_freq_dict"]):
                # if re.search(r"(?i)(Mozilla\/\d+\.\d+.*(Mobile|Android|iPhone|iPad|iPod).* (Chrome|Safari|SamsungBrowser|Edge|Opera))", ua):
                #     ua_type[subject].add("browser_mobile")
                if re.search(r"(?i)(Mozilla\/\d+\.\d+.*Windows NT \d+\.\d+.* (Chrome|Firefox|Edge|Opera|Safari))",
                             ua):
                    ua_type[subject].add("windows")
                if re.search(r"(?i)(Mozilla\/\d+\.\d+.*Linux (x86_64|i686|arm).* (Chrome|Firefox|Edge|Opera))", ua):
                    ua_type[subject].add("linux")
                if re.search(
                        r"(?i)(Mozilla\/\d+\.\d+.*Macintosh.*Mac OS X \d+_\d+.* (Chrome|Safari|Firefox|Edge|Opera))",
                        ua):
                    ua_type[subject].add("mac")
        if row.get("response_length_max"):
            if classifier.is_match_url(url):
                continue
            if subject not in url_max_resp_size:
                url_max_resp_size[subject] = dict()
            if url not in url_max_resp_size[subject]:
                url_max_resp_size[subject][url] = float(row["response_length_max"])
            else:
                url_max_resp_size[subject][url] = max(url_max_resp_size[subject][url],
                                                      float(row["response_length_max"]))

        if row.get("high_worth_api_type", "") == "jalor" and row.get("status_freq_dict"):
            status_codes_dict = json.loads(row["status_freq_dict"])
            has_2xx_code = any(code.startswith('2') or str(code) == '500' for code in status_codes_dict.keys())
            if has_2xx_code:
                if subject not in access_jalor_url_200:
                    access_jalor_url_200[subject] = set()
                access_jalor_url_200[subject].add(url)

        app_type = row.get("ai_app_type", "")
        if "external_ai" in app_type or "intranet_ai" in app_type:
            array = app_type.split("#####")
            app_type = array[0]
            ring = array[1] if len(array) > 1 else ""
            if ring == "三环":
                ring = ""
            if subject not in access_external_ai_app:
                access_external_ai_app[subject] = {"external_ai": {}, "intranet_ai": {}}
            if url not in access_external_ai_app[subject][app_type] and len(access_external_ai_app[subject][app_type]) < 4:
                access_external_ai_app[subject][app_type][url] = {
                    "appid": row.get("appid", ""),
                    "ring": ring
                }

    for subject in one_url_multiple_method:
        abnormal_url, abnormal_method = list(), list()
        for url in one_url_multiple_method[subject]:
            if (("PUT" in one_url_multiple_method[subject][url]) or (
                    "DELETE" in one_url_multiple_method[subject][url])) and \
                    (("GET" in one_url_multiple_method[subject][url]) or (
                            "POST" in one_url_multiple_method[subject][url])):
                abnormal_url.append(url)
                abnormal_method.extend(one_url_multiple_method[subject][url])
        if abnormal_url:
            if subject_type == "subject_ip":
                text = f"该IP({subject})近2小时访问{', '.join(abnormal_url)}时同时存在{'、'.join(set(abnormal_method))}请求方式"
            else:
                text = f"该账号({subject})近2小时访问{', '.join(abnormal_url)}时同时存在{'、'.join(set(abnormal_method))}请求方式"
            abnormal_desc.append(text)
    for subject in fake_xff:
        abnormal_url, abnormal_xff = list(), list()
        for url in fake_xff[subject]:
            abnormal_url.append(url)
            abnormal_xff.extend(fake_xff[subject][url])
        if abnormal_url:
            # abnormal_url = Relator.duplicate_domain_count(abnormal_url, url_access_count)
            abnormal_url = duplicate_domain_count(abnormal_url, url_access_count,
                                                          alarm["object_url_pattern"])
            if subject_type == "subject_ip":
                text = f"该IP({subject})近2小时访问{', '.join(abnormal_url[:3])}{'等' if len(abnormal_url) > 3 else ''}时使用常见伪造IP{'、'.join(set(abnormal_xff))}"
            else:
                text = f"该账号({subject})近2小时访问{', '.join(abnormal_url[:3])}{'等' if len(abnormal_url) > 3 else ''}时使用常见伪造IP{'、'.join(set(abnormal_xff))}"
            if url_access_count.get(abnormal_url[0]) > 1000:
                count_desc = [str(url_access_count.get(url, 0)) for url in abnormal_url[:3]]
                text = text + f', 且请求频次超高({",".join(count_desc)}次)'
            abnormal_desc.append(text)
    for subject in one_url_multiple_status:
        if len(one_url_multiple_status[subject]) < 5:
            break
        abnormal_status_count = dict()
        for url in one_url_multiple_status[subject]:
            for status in ["401", "403", "404", "413", "429", "421", "500", "502"]:
                if status not in abnormal_status_count:
                    abnormal_status_count[status] = one_url_multiple_status[subject][url].count(status)
                else:
                    abnormal_status_count[status] += one_url_multiple_status[subject][url].count(status)
        if sum(abnormal_status_count.values()) >= 10:
            text = list()
            if (abnormal_status_count['401'] + abnormal_status_count['403']) > 0:
                text.append(
                    f"{abnormal_status_count['401'] + abnormal_status_count['403']}次401/403状态码(可能在暴力破解或资源枚举)")
            if abnormal_status_count['404'] > 0:
                text.append(f"{abnormal_status_count['404']}次404状态码(可能为敏感资源或路径扫描探测)")
            if (abnormal_status_count['413'] + abnormal_status_count['429'] + abnormal_status_count['421']) > 0:
                text.append(
                    f"{abnormal_status_count['413'] + abnormal_status_count['429'] + abnormal_status_count['421']}次413/429/421状态码(可能存在CC攻击、拒绝服务、文件上传攻击风险)")
            if (abnormal_status_count['500'] + abnormal_status_count['502']) > 0:
                text.append(
                    f"{abnormal_status_count['500'] + abnormal_status_count['502']}次500/502状态码(可能存在应用层异常或注入攻击风险)")
            text = f"该{'IP' if subject_type == 'subject_ip' else '账号'}({subject})近2小时访问{len(one_url_multiple_status[subject])}个uri时出现{', '.join(text)}"
            abnormal_desc.append(text)
    for subject in ua_type:
        if len(ua_type[subject]) > 1:
            abnormal_desc.append(
                f"该{'IP' if subject_type == 'subject_ip' else '账号'}({subject})近2小时使用的UA跨操作系统({'、'.join(ua_type[subject])})"
            )
    for subject in one_url_multiple_status:
        abnormal_url = set()
        for url in one_url_multiple_status[subject]:
            is_2xx, is_4xx = False, False
            for status in one_url_multiple_status[subject][url]:
                if status.startswith('2'):
                    is_2xx = True
                if status.startswith('4'):
                    is_4xx = True
            if is_2xx and is_4xx:
                abnormal_url.add(url)
        if abnormal_url:
            # abnormal_url = Relator.duplicate_domain_count(list(abnormal_url), url_access_count)
            abnormal_url = duplicate_domain_count(list(abnormal_url), url_access_count,
                                                          alarm["object_url_pattern"])
            text = f"该{'IP' if subject_type == 'subject_ip' else '账号'}({subject})近2小时访问{', '.join(abnormal_url[:3])}{'等' if len(abnormal_url) > 3 else ''}时出现状态码跳变(4xx->2xx)"
            if url_access_count.get(abnormal_url[0]) > 1000:
                count_desc = [str(url_access_count.get(url, 0)) for url in abnormal_url[:3]]
                text = text + f', 且请求频次超高({",".join(count_desc)}次/h)'
            abnormal_desc.append(text)
    for subject in one_url_multiple_method:
        url_abnormal_status = dict()
        for url in one_url_multiple_method[subject]:
            top1_method = url_info.get(url, dict()).get("top_methods", [])
            top2_status = url_info.get(url, dict()).get("top_status_codes", [])
            if one_url_multiple_method[subject][url].count("POST") <= 5:
                continue
            for status in one_url_multiple_status.get(subject, dict()).get(url, list()):
                if (top1_method == ["post"]) and (status in top2_status):
                    continue
                if status == "500":
                    # if status.startswith('4') or status == "500":
                    if url not in url_abnormal_status:
                        url_abnormal_status[url] = list()
                    url_abnormal_status[url].append(status)
        abnormal_url = duplicate_domain_count(list(url_abnormal_status.keys()), url_access_count,
                                                      alarm["object_url_pattern"])
        if abnormal_url:
            text = f"该{'IP' if subject_type == 'subject_ip' else '账号'}({subject})近2小时访问如下url时出现大量POST请求" \
                   f",且伴随异常状态码,请警惕关键业务数据被篡改风险。"
            text_details = list()
            for index, url in enumerate(abnormal_url[:3]):
                text_detail = f'\n{index + 1}）{url}{":属于关键靶标" if url_info.get(url, dict()).get("attack_hw_target") else ""}' \
                              f'\n-- 本次访问：近2小时出现{one_url_multiple_method[subject][url].count("POST")}次POST请求,' \
                              f'伴随异常状态码({",".join(set(url_abnormal_status[url]))})'
                if url_access_count[url] > 1000:
                    text_detail += f",请求频次超高({url_access_count[url]}次)"
                if url_info.get(url, dict()).get("baseline") and (
                        sum(subject_access_url_count[subject][url]) > url_info[url]["baseline"]):
                    text_detail += f",请求次数较群体热力偏高({sum(subject_access_url_count[subject][url])}次)"
                text_detail += f"\n-- url_pattern基线：top请求方式为{url_info.get(url, dict()).get('top_methods', []) or ''}," \
                               f"top2状态码为{url_info.get(url, dict()).get('top_status_codes', '未知')}, " \
                               f"2小时人均访问量为{math.ceil(url_info.get(url, dict()).get('baseline', 0))}"
                text_details.append(text_detail)
            text += ''.join(text_details)
            abnormal_desc.append(text)
    for subject in url_max_resp_size:
        abnormal_url = dict()
        for url in url_max_resp_size[subject]:
            if url_info.get(url, dict()).get("latest_7d_resp_size_avg") and (
                    url_max_resp_size[subject][url] / url_info[url]["latest_7d_resp_size_avg"]) > 5:
                if url_info.get(url, dict()).get("high_worth_api_type") or \
                        url_info.get(url, dict()).get("attack_hw_target") or \
                        (sum(subject_access_url_count[subject][url]) > 1000) or \
                        check_multi_url_consistency(url, alarm["object_url_pattern"], url_info) or \
                        ((url_info.get(url, dict()).get("baseline") != 0) and (
                                sum(subject_access_url_count[subject][url]) > url_info[url]["baseline"])):
                    abnormal_url[url] = url_max_resp_size[subject][url]
        if abnormal_url:
            urls = duplicate_domain_crawler(abnormal_url, alarm["object_url_pattern"])
            text = f"该{subject_type_str}（{subject}）近2小时内访问如下url时回包长度远超历史平均水平："
            text_details = list()
            for index, url in enumerate(urls[:3]):
                is_url_consistency = check_multi_url_consistency(url, alarm["object_url_pattern"], url_info)
                url_consistency_tag = "（客体相关URL）" if is_url_consistency else ""
                interface_info = list()
                text_detail = f"\n{index + 1}){url}{url_consistency_tag}："
                if url_info.get(url, dict()).get("high_worth_api_type"):
                    interface_info.append("涉隐")
                if url_info.get(url, dict()).get("attack_hw_target"):
                    interface_info.append(f"属于关键靶标({url_info[url]['attack_hw_target']})")
                if interface_info:
                    text_detail = text_detail + '/'.join(interface_info) + "；"
                text_detail += f"近2小时最大回包长度为{abnormal_url[url]}（近7天平均长度：{url_info.get(url, dict()).get('latest_7d_resp_size_avg', 0)}）；"
                sum_access_count = sum(subject_access_url_count[subject][url])
                text_detail += f"请求{sum_access_count}次"
                if sum_access_count > 1000:
                    text_detail += f"，频次超高"
                if url_info.get(url, dict()).get("baseline") and (sum_access_count > url_info.get(url, dict()).get('baseline', 0)):
                    text_detail += f"，较群体热力偏高"
                text_detail += f"（人均访问量：{math.ceil(url_info.get(url, dict()).get('baseline', 0))}）；"
                text_details.append(text_detail)
            text += (''.join(text_details))
            abnormal_desc.append(text)
    talk_cnt1, talk_cnt2 = 1, 1
    for subject in subject_access_url_count:
        over_talk, not_over_talk = list(), list()
        for url in subject_access_url_count[subject]:
            if url in alarm["object_url_pattern"]:
                subject_access_sum_times = sum(subject_access_url_count[subject][url])
                baseline_times = float(url_info.get(url, {}).get('baseline', 0))
                create_time = (url_info.get(url, {}).get('create_time') or " ").split(' ')[0]
                if subject_access_sum_times > baseline_times and talk_cnt1 <= 3:
                    jixian = ""
                    # 如果主体访问量 / 基线 >= 20，或者基线为0,则评分 + 5
                    if baseline_times == 0 or (subject_access_sum_times / baseline_times) >= 20:
                        jixian = "_基线"
                    over_talk.append(f"\n{len(over_talk) + 1}){url}：{subject_access_sum_times}次 "
                                     f"（人均访问量_2h{jixian}：{math.ceil(baseline_times)}；"
                                     f"近期总访问量_7d：{math.ceil(float(url_info.get(url, {}).get('latest_7d_count', 0)))}；"
                                     f"近期总访问量_24h：{math.ceil(float(url_info.get(url, {}).get('latest_24h_count', 0)))}；"
                                     f"请求方式：{url_info.get(url, {}).get('top_methods', '')}；"
                                     f"首次纳入统计时间：{create_time}）")
                    talk_cnt1 += 1
                elif talk_cnt2 <= 3:
                    not_over_talk.append(f"\n{len(not_over_talk) + 1}){url}：{subject_access_sum_times}次 "
                                         f"（人均访问量_2h：{math.ceil(baseline_times)}；"
                                         f"近期总访问量_7d：{math.ceil(float(url_info.get(url, {}).get('latest_7d_count', 0)))}；"
                                         f"近期总访问量_24h：{math.ceil(float(url_info.get(url, {}).get('latest_24h_count', 0)))}；"
                                         f"请求方式：{url_info.get(url, {}).get('top_methods', '')}；"
                                         f"首次纳入统计时间：{create_time}）")
                    talk_cnt2 += 1

        if over_talk:
            abnormal_desc.append(f"该{subject_type_str}（{subject}）近2小时高频访问如下接口{''.join(over_talk)}")
        if not_over_talk:
            abnormal_desc.append(f"该{subject_type_str}（{subject}）近2小时访问如下接口，未偏离群体热力{''.join(not_over_talk)}")

    for subject in access_jalor_url_200:
        if len(access_jalor_url_200[subject]) > 0:
            urls = '，'.join(list(access_jalor_url_200[subject])[:3])
            elide = ' 等' if len(access_jalor_url_200[subject]) > 3 else ''
            abnormal_desc.append(
                f"该{subject_type_str}({subject})近2小时内有成功访问jalor高价值接口（比如： {urls}{elide}）"
            )
    append_jalor_url_desc(alarm, subject_type, abnormal_desc)
    for subject, types in access_external_ai_app.items():
        if types.get("external_ai"):
            target_type = "external_ai"
        elif types.get("intranet_ai"):
            target_type = "intranet_ai"
        else:
            continue
        all_urls = list(types[target_type].keys())
        display_urls = all_urls[:3]
        formatted_parts = []
        for url in display_urls:
            info = types[target_type][url]
            # 这里的格式可以根据喜好调整，例如：url 「应用名 | ID:123」
            ring_text = f"|{info['ring']}" if info['ring'] else ""
            formatted_parts.append(f"{url}(应用:{info['appid']}{ring_text}）")
        content = ", ".join(formatted_parts)
        suffix = "等" if len(all_urls) > 3 else ""
        type_name = "外边界" if target_type == "external_ai" else ""
        abnormal_desc.append(f"该{subject_type_str}（{subject}）近2小时内有访问{type_name}AIGC应用，比如：{content}{suffix}")


    batch_crawling_url_substrings = ["{num}", "(w3Account)", "userinfo", "personinfo", "page"]
    for subject, urls in subject_access_url_count.items():
        suspicious_url = dict()
        is_url_consistency = False
        for url, count_list in urls.items():
            if any(substring.lower() in str(url).lower() for substring in batch_crawling_url_substrings) and sum(count_list) >= 80:
                if check_multi_url_consistency(url, alarm["object_url_pattern"], url_info):
                    is_url_consistency = True
                suspicious_url[url] = sum(count_list)
                if len(suspicious_url) == 3:
                    break
        if suspicious_url:
            url_consistency_tag = "（含客体相关URL）" if is_url_consistency else ""
            url_count_str = "，".join([f"{url}（{count}次）" for url, count in suspicious_url.items()])
            abnormal_desc.append(
                f"该{subject_type_str}（{subject}）近2小时内大量请求{url_count_str}，疑似进行批量爬取{url_consistency_tag}")
    return abnormal_desc

def query_intranet_ips(es, ips: list[str]):
    if not ips:
        return {}
    query = {
        "size": len(ips),
        "query": {
            "terms": {"ip": ips}
        }
    }
    return es.search(index="t_int_ip_info", body=query)

def duplicate_domain(urls: list) -> list:
    # 取前n个url 要保证域名多样性
    head, tail = list(), list()
    temp_domain = set()
    for url in urls:
        domain = url.split("/")[2]
        if domain not in temp_domain:
            temp_domain.add(domain)
            head.append(url)
        else:
            tail.append(url)
    head.extend(tail)
    return head


def get_sensitive_target_access(es_data, subject_type):
    # 计算涉密 靶标类访问行为
    sensitive_api = dict()
    target_api = dict()
    abnormal_desc = list()
    for row in es_data["hits"]["hits"]:
        row = row["_source"]
        subject = row[subject_type]
        url = row["url_pattern"]
        if row.get("high_worth_api_type") == "涉隐":
            if subject not in sensitive_api:
                sensitive_api[subject] = set()
            sensitive_api[subject].add(url)
        if row.get("attack_hw_target"):
            if subject not in target_api:
                target_api[subject] = set()
            target_api[subject].add(f"{url}({row['attack_hw_target']})")
    for subject in sensitive_api:
        abnormal_url = duplicate_domain(list(sensitive_api[subject]))
        text = f"该{'IP' if subject_type == 'subject_ip' else '账号'}({subject})近2小时内请求{len(abnormal_url)}" \
               f"个涉隐接口(比如: {', '.join(abnormal_url[:3])})"
        abnormal_desc.append(text)
    for subject in target_api:
        abnormal_url = duplicate_domain(list(target_api[subject]))
        text = f"该{'IP' if subject_type == 'subject_ip' else '账号'}({subject})近2小时内有访问靶标url" \
               f"(比如:{', '.join(abnormal_url[:3])})"
        abnormal_desc.append(text)
    return abnormal_desc

def access_domain(es_data, subject_type) -> str:
    # 泛扫域名
    res = set()
    for row in es_data["hits"]["hits"]:
        row = row["_source"]
        subject = row.get(subject_type)
        if row.get("url_pattern", "").endswith(".com") or row.get("url_pattern").endswith(".cn"):
            res.add(row["url_pattern"].split("/")[-1])
    if len(res) > 10:
        return f"该{'IP' if subject_type == 'subject_ip' else '账号'}({subject})近2小时疑似泛扫, 访问了{len(res)}个域名:{';'.join(list(res)[:3])}"
    return ""

def run_access_jalor_case(alarm):
    es_index = "xxx"
    scripts["query"]["bool"]["must"][1] = {"match": {"subject_account": alarm["subject_account"]}}
    es_data = es.search(index=es_index, body=scripts, size=1000000)
    if es_data["hits"]["total"]["value"] > 0:
        url_info = get_url_latest_7d_resp_size_avg_batch(es, es_data, alarm["object_url_pattern"])
        intranet_dmz_ips = select_intranet_dmz_ips(es, es_data)
        res = get_subject_access_url_features(es_data, "subject_account", url_info, alarm,
                                                      intranet_dmz_ips)
        sensitive_target_access = get_sensitive_target_access(es_data, "subject_account")
        return {
            "subject_access_url": res,
            "sensitive_target_access": sensitive_target_access,
            "access_domain": access_domain(es_data, "subject_account")
        }