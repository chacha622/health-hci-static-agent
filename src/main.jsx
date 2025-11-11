import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

// 读取 public/data/latest.json
const DATA_URL = (import.meta.env.BASE_URL || "/") + "data/latest.json";

// 小徽标
function Tag({ children, className = "" }) {
  return (
    <span className={`px-2 py-0.5 text-xs rounded-full bg-gray-200 ${className}`}>
      {children}
    </span>
  );
}

// 页头
function Header() {
  return (
    <header className="py-6">
      <h1 className="text-2xl font-bold">Health-HCI PhD Agent</h1>
      <p className="text-sm text-gray-600">
        Daily updated <b>Health-HCI & Information Design</b> PhD opportunities —
        <b> ETH / Melbourne / EU</b> focus
        <br />
        每日更新的健康HCI与信息传达设计相关博士机会（优先：ETH / 墨尔本 / 欧洲）
      </p >
    </header>
  );
}

// 本地画像关键词（你原来的逻辑保留）
function useLocalProfile() {
  const KEY = "profile_keywords";
  const [list, setList] = useState(() => {
    try {
      return (
        JSON.parse(localStorage.getItem(KEY)) || [
          "information design",
          "health communication",
          "AI chatbot",
          "patient engagement",
        ]
      );
    } catch {
      return [
        "information design",
        "health communication",
        "AI chatbot",
        "patient engagement",
      ];
    }
  });
  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(list));
  }, [list]);
  return [list, setList];
}

// 顶部筛选条（新增：Only New / Source Type）
function Filters({ params, setParams }) {
  return (
    <div className="flex gap-3 flex-wrap items-end bg-white rounded-2xl shadow p-4">
      <div>
        <label className="text-xs text-gray-500">Funding 资助</label>
        <select
          className="block border rounded px-3 py-2"
          value={params.hasFunding}
          onChange={(e) => setParams((p) => ({ ...p, hasFunding: e.target.value }))}
        >
          <option value="">All 全部</option>
          <option value="1">Has funding 有资助</option>
          <option value="0">No/Unknown 无明确资助</option>
        </select>
      </div>

      <div>
        <label className="text-xs text-gray-500">Min Score 最低分</label>
        <input
          className="border rounded px-3 py-2 w-28"
          type="number"
          value={params.minScore}
          onChange={(e) => setParams((p) => ({ ...p, minScore: e.target.value }))}
        />
      </div>

      <div>
        <label className="text-xs text-gray-500">Source 来源</label>
        <select
          className="block border rounded px-3 py-2"
          value={params.sourceType}
          onChange={(e) => setParams((p) => ({ ...p, sourceType: e.target.value }))}
        >
          <option value="all">All 全部</option>
          <option value="academic">Academic only 仅学术站</option>
          <option value="social">Social only 仅社交源</option>
        </select>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={params.onlyNew}
          onChange={(e) => setParams((p) => ({ ...p, onlyNew: e.target.checked }))}
        />
        Only New 只看新增
      </label>

      <button
        className="px-4 py-2 rounded-xl bg-black text-white"
        onClick={() => setParams((p) => ({ ...p }))}
      >
        Apply 应用
      </button>
    </div>
  );
}

// 画像关键词编辑
function ProfileEditor({ list, setList }) {
  const [val, setVal] = useState("");
  const remove = (idx) => setList(list.filter((_, i) => i !== idx));
  const add = () => {
    if (!val.trim()) return;
    setList([...list, val.trim()]);
    setVal("");
  };
  return (
    <div className="bg-white rounded-2xl shadow p-5 space-y-3">
      <div className="text-lg font-semibold">Profile Keywords 画像关键词</div>
      <div className="flex gap-2 flex-wrap">
        {list.map((k, i) => (
          <span
            key={i}
            className="px-2 py-1 rounded-full bg-indigo-100 text-indigo-700 text-sm"
          >
            {k}{" "}
            <button className="ml-2 text-indigo-700" onClick={() => remove(i)}>
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          className="border rounded px-3 py-2 flex-1"
          placeholder="Add / 添加…"
          value={val}
          onChange={(e) => setVal(e.target.value)}
        />
        <button className="px-4 py-2 rounded-xl bg-indigo-600 text-white" onClick={add}>
          Add
        </button>
      </div>
      <div className="text-xs text-gray-500">
        示例：information design, health communication, AI chatbot, patient engagement…（仅保存在本地浏览器）
      </div>
    </div>
  );
}

// 单条卡片（新版字段：ai_summary / summary / papers / source / score / is_new）
function Card({ item, profile }) {
  // 兼容旧字段名
  const university =
    item.university || item.org || item.school || "Unknown University";
  const link = item.link || item.url || "#";
  const funding = item.funding || item.fund || "TBD";
  const deadline = item.deadline || "Rolling";
  const source = item.source || "source";
  const score = item.score ?? item.match_score ?? 0;
  const isNew = !!item.is_new;
  const aiSummary = item.ai_summary;
  const summary = item.summary;

  // 画像命中高亮（向后兼容 profile_hits）
  const hits = (item.profile_hits || "")
    .toLowerCase()
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const hasHit =
    hits.length > 0 &&
    profile.some((p) => hits.some((h) => h.includes(p.toLowerCase())));

  return (
    <div
      className={
        "bg-white rounded-2xl shadow p-5 space-y-2 hover:shadow-lg transition " +
        (hasHit ? "ring-2 ring-indigo-300" : "")
      }
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-lg font-semibold">{university}</h3>
        <div className="flex items-center gap-2">
          {isNew && <Tag className="bg-green-100 text-green-700">NEW</Tag>}
          <Tag className="bg-slate-100 text-slate-700">{source}</Tag>
          <Tag className="bg-indigo-100 text-indigo-700">Score: {score}</Tag>
        </div>
      </div>

      <a
        href= "_blank"
        rel="noopener noreferrer"
        className="text-sm text-blue-600 underline break-all"
      >
        {link}
      </a >

      <div className="text-sm text-gray-700">
        <div>
          <b>Funding:</b> {funding}
        </div>
        <div>
          <b>Deadline:</b> {deadline}
        </div>
      </div>

      {/* 智能摘要优先，其次规则摘要 */}
      {aiSummary && <p className="mt-2 text-sm text-gray-700">{aiSummary}</p >}
      {!aiSummary && summary && (
        <p className="mt-2 text-sm text-gray-700">{summary}</p >
      )}

      {/* 代表论文 */}
      {Array.isArray(item.papers) && item.papers.length > 0 && (
        <div className="mt-2">
          <div className="text-xs font-medium text-slate-500 mb-1">
            Representative papers
          </div>
          <ul className="text-xs list-disc list-inside text-blue-700 space-y-1">
            {item.papers.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 兼容旧：画像命中的标签展示 */}
      {hits.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          {hits.slice(0, 6).map((k, i) => (
            <Tag key={i}>{k}</Tag>
          ))}
        </div>
      )}
    </div>
  );
}

function App() {
  const [data, setData] = useState({ items: [], by_source: {}, total_items: 0 });
  const [loading, setLoading] = useState(true);
  const [params, setParams] = useState({
    hasFunding: "",
    minScore: 0,
    sourceType: "all", // all / academic / social
    onlyNew: false,
  });
  const [profile, setProfile] = useLocalProfile();

  useEffect(() => {
    fetch(DATA_URL)
      .then((r) => r.json())
      .then((js) => setData(js || { items: [], by_source: {}, total_items: 0 }))
      .catch(() => setData({ items: [], by_source: {}, total_items: 0 }))
      .finally(() => setLoading(false));
  }, []);

  const items = useMemo(() => {
    let arr = [...(data.items || [])];

    // Source 过滤
    if (params.sourceType === "academic") {
      arr = arr.filter((x) => !x.social);
    } else if (params.sourceType === "social") {
      arr = arr.filter((x) => x.social);
    }

    // Only New
    if (params.onlyNew) {
      arr = arr.filter((x) => x.is_new);
    }

    // Funding
    if (params.hasFunding !== "") {
      const wantFunded = params.hasFunding === "1";
      arr = arr.filter((x) => {
        const f = (x.funding || "").toLowerCase();
        const isFunded =
          f.includes("funded") ||
          f.includes("studentship") ||
          f.includes("stipend") ||
          f.includes("scholarship") ||
          f.includes("full");
        return wantFunded ? isFunded : !isFunded;
      });
    }

    // Min score
    const ms = parseInt(params.minScore || 0, 10);
    if (ms > 0) {
      arr = arr.filter((x) => (x.score ?? x.match_score ?? 0) >= ms);
    }

    return arr;
  }, [data, params]);

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <Header />

      <Filters params={params} setParams={setParams} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ProfileEditor list={profile} setList={setProfile} />
        <div className="bg-white rounded-2xl shadow p-5">
          <div className="text-sm text-gray-600">
            更新时间 Updated: {data.generated_at || "—"} · 共{" "}
            {data.total_items || data.count || (data.items?.length || 0)} 条
          </div>
          <div className="text-xs text-gray-500 mt-2">
            数据源（按条数）：{" "}
            {data.by_source
              ? Object.entries(data.by_source)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ")
              : "—"}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-sm text-gray-500 py-10">Loading…</div>
      ) : (
        <section className="grid grid-cols-1 md:grid-cols-2 xl-grid-cols-3 gap-4">
          {items.map((it, idx) => (
            <Card key={it.id || idx} item={it} profile={profile} />
          ))}
        </section>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
