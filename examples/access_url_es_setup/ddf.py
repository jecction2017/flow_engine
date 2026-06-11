EXCLUDED_APPID = "com.cc.all"


def _safe_source(hit):
    if type(hit) != "dict":
        return {}
    src = hit.get("_source")
    return src if type(src) == "dict" else {}


def _to_int(v, default=0):
    if v == None:
        return default
    if type(v) == "int":
        return v
    if type(v) == "float":
        return int(v)
    if type(v) == "string":
        if v == "":
            return default
        return int(v)
    return default


def _to_float(v, default=0.0):
    if v == None:
        return default
    if type(v) == "float":
        return v
    if type(v) == "int":
        return float(v)
    if type(v) == "string":
        if v == "":
            return default
        return float(v)
    return default


def _to_str(v):
    if v == None:
        return ""
    return str(v)


def _safe_map(v):
    return v if type(v) == "dict" else {}


def _contains_any(s, needles):
    text = _to_str(s).lower()
    for needle in needles:
        if _to_str(needle).lower() in text:
            return True
    return False


def _contains_suffix(url, suffixes):
    text = _to_str(url).lower()
    for suffix in suffixes:
        sf = _to_str(suffix).lower()
        if sf == "":
            continue
        if text.endswith(sf):
            return True
    return False


def _sum_status_prefix(status_map, prefix):
    if type(status_map) != "dict":
        return 0
    total = 0
    for key, one in status_map.items():
        if _to_str(key).startswith(prefix):
            total += _to_int(one, 0)
    return total


def _sum_status_keys(status_map, keys):
    if type(status_map) != "dict":
        return 0
    total = 0
    for key in keys:
        total += _to_int(status_map.get(key), 0)
    return total


def _sum_method_keys(method_map, keys):
    if type(method_map) != "dict":
        return 0
    total = 0
    for key in keys:
        total += _to_int(method_map.get(key), 0)
    return total


def _is_private_172(ip):
    parts = _to_str(ip).split(".")
    if len(parts) < 2:
        return False
    if not _to_str(ip).startswith("172."):
        return False
    second = _to_int(parts[1], -1)
    return second >= 16 and second <= 31


def _is_fake_xff_ip(ip):
    ip_str = _to_str(ip)
    if ip_str == "":
        return False
    return (
        ip_str.startswith("10.")
        or ip_str.startswith("127.")
        or ip_str.startswith("192.168.")
        or ip_str == "1.1.1.1"
        or _is_private_172(ip_str)
    )


def _count_fake_xff(xff_map, dmz_ip_set, is_intranet):
    if type(xff_map) != "dict":
        return 0
    if _to_str(is_intranet) == "1":
        return 0
    cnt = 0
    for ip, one in xff_map.items():
        ip_str = _to_str(ip)
        if _is_fake_xff_ip(ip_str) and (ip_str not in dmz_ip_set):
            cnt += _to_int(one, 0)
    return cnt


def _extract_domain(url):
    text = _to_str(url).strip()
    if text == "":
        return ""
    if "://" in text:
        host_part = text.split("://", 2)[1]
    else:
        host_part = text
    host = host_part.split("/", 2)[0]
    if ":" in host:
        return host.split(":", 2)[0]
    return host


def _split_lines(raw):
    s = _to_str(raw)
    if s == "":
        return []
    return s.split("\n")


def _extract_top_tokens(raw, limit_n):
    out = []
    if type(raw) == "list":
        for item in raw:
            token = _to_str(item).strip().lower()
            if token != "":
                out = out + [token]
            if len(out) >= limit_n:
                break
        return out
    for line in _split_lines(raw):
        token = _to_str(line).split(":", 2)[0].strip().lower()
        if token != "":
            out = out + [token]
        if len(out) >= limit_n:
            break
    return out


def _build_url_info_map(url_info_hits):
    out = {}
    for hit in (url_info_hits or []):
        src = _safe_source(hit)
        url = _to_str(src.get("url_pattern"))
        if url == "":
            continue
        ip_7d_dc = _to_float(src.get("ip_7d_dc"), 0.0)
        latest_7d_count = _to_float(src.get("latest_7d_count"), 0.0)
        baseline = 0.0
        if ip_7d_dc != 0:
            baseline = (latest_7d_count / ip_7d_dc) * 0.8 / (24 * 7 * 0.2) * 2
        out[url] = {
            "app_id": _to_str(src.get("app_id")),
            "latest_7d_resp_size_avg": _to_float(src.get("latest_7d_resp_size_avg"), 0.0),
            "baseline": baseline,
            "top_methods": _extract_top_tokens(src.get("top_methods"), 1),
            "top_status_codes": _extract_top_tokens(src.get("top_status_codes"), 2),
        }
    return out


def _build_dmz_ip_set(dmz_hits):
    out = {}
    for hit in (dmz_hits or []):
        src = _safe_source(hit)
        ip = _to_str(src.get("ip"))
        area = _to_str(src.get("network_area")).lower()
        if ip != "" and ("dmz" in area):
            out[ip] = 1
    return out


def _url_consistent(url1, url2, url_info_map):
    if url1 == url2:
        return True
    domain1 = _extract_domain(url1)
    domain2 = _extract_domain(url2)
    if domain1 != "" and domain1 == domain2:
        return True
    info1 = url_info_map.get(_to_str(url1), {})
    info2 = url_info_map.get(_to_str(url2), {})
    app1 = _to_str(info1.get("app_id"))
    app2 = _to_str(info2.get("app_id"))
    return app1 != "" and app1 == app2 and app1 != EXCLUDED_APPID


def _multi_url_consistent(url, alarm_urls, url_info_map):
    for one in (alarm_urls or []):
        if _url_consistent(_to_str(url), _to_str(one), url_info_map):
            return True
    return False


def _parse_ai_type(ai_type):
    text = _to_str(ai_type)
    if text == "":
        return {"is_external_ai": 0, "is_intranet_ai": 0, "is_external_ai_non_third_ring": 0}
    parts = text.split("#####")
    ai = _to_str(parts[0]).lower()
    ring = _to_str(parts[1]) if len(parts) > 1 else ""
    if ring == "三环":
        ring = ""
    is_external = 1 if ai == "external_ai" else 0
    is_intranet = 1 if ai == "intranet_ai" else 0
    return {
        "is_external_ai": is_external,
        "is_intranet_ai": is_intranet,
        "is_external_ai_non_third_ring": 1 if (is_external == 1 and ring != "") else 0,
    }


def _is_resp_size_url_excluded(url):
    # Equivalent intent to old URLClassifier: media/streaming/static/cc URLs
    # should not participate in response-size spike detection.
    lower_url = _to_str(url).lower()
    if _contains_any(lower_url, ["/image/", "/video/", "/pdf/"]):
        if _contains_any(lower_url, ["resize", "crop", "thumb", "compress", "segment", "clip", "transcode", "preview", "convert", "merge"]):
            return True
    if _contains_any(lower_url, ["/ws/", "/socket.io/", "/stream/", "/chunk/"]):
        return True
    if _contains_any(lower_url, ["/static/", "/media/"]):
        return True
    if _contains_any(lower_url, ["onebox.cc.com", "clouddrive", ".cc.com", "edm"]):
        if _contains_any(lower_url, [".cc.com"]):
            return True
    if _contains_suffix(
        lower_url,
        [
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".css", ".js",
            ".woff", ".ttf", ".eot", ".mp4", ".mp3", ".pdf", ".zip", ".gz",
        ],
    ):
        return True
    return False


def _make_row(src, subject_field, alarm_urls, url_info_map, dmz_ip_set):
    subject = src.get(subject_field)
    url = src.get("url_pattern")
    if subject == None or url == None:
        return None
    status_map = _safe_map(src.get("status_freq_dict"))
    method_map = _safe_map(src.get("method_freq_dict"))
    xff_map = _safe_map(src.get("xff_freq_dict"))
    ai = _parse_ai_type(src.get("ai_app_type"))
    url_str = _to_str(url)
    side = url_info_map.get(url_str, {})
    top_methods = side.get("top_methods", [])
    top_status_codes = side.get("top_status_codes", [])
    is_alarm_consistent = 1 if _multi_url_consistent(url_str, alarm_urls, url_info_map) else 0
    row_weight = _to_int(src.get("count"), 1)
    has_high_worth = 1 if _to_str(src.get("high_worth_api_type")) != "" else 0
    has_attack_target = 1 if _to_str(src.get("attack_hw_target")) != "" else 0
    resp_size_candidate = 0 if _is_resp_size_url_excluded(url_str) else 1
    return {
        "subject": _to_str(subject),
        "url_pattern": url_str,
        "row_weight": row_weight,
        "response_length_max": _to_float(src.get("response_length_max"), 0.0),
        "latest_7d_resp_size_avg": _to_float(side.get("latest_7d_resp_size_avg"), _to_float(src.get("latest_7d_resp_size_avg"), 0.0)),
        "url_baseline_2h": _to_float(side.get("baseline"), _to_float(src.get("baseline"), 0.0)),
        "status_2xx_count": _sum_status_prefix(status_map, "2"),
        "status_4xx_count": _sum_status_prefix(status_map, "4"),
        "status_5xx_count": _sum_status_prefix(status_map, "5"),
        "status_500_count": _to_int(status_map.get("500"), 0),
        "status_401_403_count": _sum_status_keys(status_map, ["401", "403"]),
        "status_404_count": _to_int(status_map.get("404"), 0),
        "status_413_429_421_count": _sum_status_keys(status_map, ["413", "429", "421"]),
        "post_count": _to_int(method_map.get("POST"), 0),
        "put_delete_count": _sum_method_keys(method_map, ["PUT", "DELETE"]),
        "get_post_mix": 1 if (_to_int(method_map.get("GET"), 0) > 0 and _to_int(method_map.get("POST"), 0) > 0) else 0,
        "fake_xff_count": _count_fake_xff(xff_map, dmz_ip_set, src.get("is_intranet")),
        "is_batch_crawl_url": 1 if _contains_any(url_str, ["{num}", "(w3Account)", "userinfo", "personinfo", "page"]) else 0,
        "is_jalor_url": 1 if _to_str(src.get("high_worth_api_type")) == "jalor" else 0,
        "has_high_worth": has_high_worth,
        "has_attack_target": has_attack_target,
        "weighted_has_high_worth": row_weight if has_high_worth == 1 else 0,
        "weighted_has_attack_target": row_weight if has_attack_target == 1 else 0,
        "resp_size_candidate": resp_size_candidate,
        "is_alarm_url_consistent": is_alarm_consistent,
        "baseline_top_method_post": 1 if (len(top_methods) > 0 and _to_str(top_methods[0]) == "post") else 0,
        "baseline_status_500_common": 1 if ("500" in top_status_codes) else 0,
        "is_external_ai": ai["is_external_ai"],
        "is_intranet_ai": ai["is_intranet_ai"],
        "is_external_ai_non_third_ring": ai["is_external_ai_non_third_ring"],
    }


def build_dataset(es_data, subject_field, alarm, url_info_hits, dmz_hits):
    hits = (((es_data or {}).get("hits") or {}).get("hits")) or []
    alarm_urls = (alarm or {}).get("object_url_pattern") or []
    url_info_map = _build_url_info_map(url_info_hits)
    dmz_ip_set = _build_dmz_ip_set(dmz_hits)
    rows = []
    for hit in hits:
        src = _safe_source(hit)
        row = _make_row(src, subject_field, alarm_urls, url_info_map, dmz_ip_set)
        if row != None:
            rows.append(row)

    return {
        "dataset_id": "access_url",
        "rows": rows,
        "timestamp_field": None,
        "weight_field": "row_weight",
    }

def _unwrap_data(resp):
  if type(resp) != "dict":
    return {}
  if "ok" in resp and resp["ok"] and type(resp.get("data")) == "dict":
    return resp["data"]
  return {}

def _safe_source(hit):
  if type(hit) != "dict":
    return {}
  src = hit.get("_source")
  return src if type(src) == "dict" else {}

def _collect_unique_values(hits, field_name):
  out = []
  seen = {}
  for hit in hits:
    src = _safe_source(hit)
    value = src.get(field_name)
    if value == None:
      continue
    key = str(value)
    if key in seen:
      continue
    seen[key] = 1
    out.append(key)
  return out

def _collect_unique_xff_ips(hits):
  out = []
  seen = {}
  for hit in hits:
    src = _safe_source(hit)
    xff_map = src.get("xff_freq_dict")
    if type(xff_map) != "dict":
      continue
    for ip, _ in xff_map.items():
      key = str(ip)
      if key in seen:
        continue
      seen[key] = 1
      out.append(key)
  return out

def _merge_unique(values, extra_values):
  out = []
  seen = {}
  for v in values:
    key = str(v)
    if key in seen:
      continue
    seen[key] = 1
    out.append(key)
  for v in (extra_values or []):
    key = str(v)
    if key in seen:
      continue
    seen[key] = 1
    out.append(key)
  return out

def _fetch_terms_hits(index_name, term_field, values, source_fields):
  if len(values) == 0:
    return []
  hits = []
  batch = []
  for value in values:
    batch = batch + [value]
    if len(batch) >= 5000:
      resp = es_search(
        resolve("$.global.es_instance"),
        index_name,
        body={"_source": source_fields},
        query={"terms": {term_field: batch}},
        size=1000000,
      )
      data = _unwrap_data(resp)
      for one in ((((data.get("hits") or {}).get("hits")) or [])):
        hits.append(one)
      batch = []
  if len(batch) > 0:
    resp = es_search(
      resolve("$.global.es_instance"),
      index_name,
      body={"_source": source_fields},
      query={"terms": {term_field: batch}},
      size=1000000,
    )
    data = _unwrap_data(resp)
    for one in ((((data.get("hits") or {}).get("hits")) or [])):
      hits.append(one)
  return hits

def _build_main_query():
  must_filters = [
    {"range": {"@timestamp": {"gte": resolve("$.global.query_window.gte"), "lte": resolve("$.global.query_window.lte")}}}
  ]
  alarm = resolve("$.global.alarm")
  subject_field = resolve("$.global.subject_type")
  if type(alarm) == "dict":
    subject_value = alarm.get(subject_field)
    if subject_value != None and str(subject_value) != "":
      must_filters.append({"term": {subject_field: subject_value}})
  return {"bool": {"filter": must_filters}}

def run():
  q = _build_main_query()
  log_info(q)
  # Memory-oriented layout:
  # - keep large payload in local vars, avoid writing full datasets to global context.
  # - only final findings and diagnostics are exported.
  scroll_resp = es_scroll(
    resolve("$.global.es_instance"),
    resolve("$.global.es_index"),
    body={
      "_source": [
        resolve("$.global.subject_type"),
        "url_pattern",
        "count",
        "status_freq_dict",
        "method_freq_dict",
        "xff_freq_dict",
        "is_intranet",
        "response_length_max",
        "high_worth_api_type",
        "attack_hw_target",
        "ai_app_type",
      ]
    },
    query=q,
    size=5000,
    scroll_ttl="2m",
  )
  log_info(scroll_resp)
  scroll_data = _unwrap_data(scroll_resp)
  if scroll_data.get("_scroll_truncated", False):
    fail("es_scroll truncated: source data is incomplete, please increase connector max_scroll_pages or narrow query window")
  hits = (((scroll_data.get("hits") or {}).get("hits")) or [])
  urls = _collect_unique_values(hits, "url_pattern")
  alarm = resolve("$.global.alarm")
  if type(alarm) == "dict":
    urls = _merge_unique(urls, alarm.get("object_url_pattern"))
  xff_ips = _collect_unique_xff_ips(hits)

  url_info_hits = _fetch_terms_hits(
    "t_url_info",
    "url_pattern",
    urls,
    ["url_pattern", "latest_7d_resp_size_avg", "latest_7d_count", "latest_24h_count", "ip_7d_dc", "top_methods", "top_status_codes", "create_time", "app_id"],
  )
  log_info(url_info_hits)
  log_info(xff_ips)
  dmz_hits = _fetch_terms_hits(
    "t_int_ip_info",
    "ip",
    xff_ips,
    ["ip", "network_area"],
  )
  log_info(dmz_hits)
  dataset = build_dataset(scroll_data, resolve("$.global.subject_type"), resolve("$.global.alarm"), url_info_hits, dmz_hits)
  detail_output = feature_pipeline(dataset, dictionary_name=resolve("$.global.scene_detail"))
  subject_output = feature_pipeline(dataset, dictionary_name=resolve("$.global.scene_subject"))
  findings = detail_output.get("matches", []) + subject_output.get("matches", [])
  return {
    "findings": findings,
    "scroll_pages_fetched": scroll_data.get("pages_fetched", 0),
    "scroll_truncated": scroll_data.get("_scroll_truncated", False),
    "source_hit_count": len(hits),
  }

run()