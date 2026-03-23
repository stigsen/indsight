// Extension: survey-indsight
// Survey data analysis skill for SurveyXact datasets — query, graph, summarize, find outliers

import { joinSession } from "@github/copilot-sdk/extension";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";

// ─── XML Dataset Parser ───────────────────────────────────────────────────────
// Parses the SurveyXact Excel-XML export format (SpreadsheetML)

function extractSheetRows(xml, sheetName) {
    const sheetRe = new RegExp(
        `ss:Name="${sheetName}"[\\s\\S]*?<\\/Table>`
    );
    const sheetMatch = xml.match(sheetRe);
    if (!sheetMatch) return [];

    const rows = [];
    const rowRe = /<Row[^>]*>([\s\S]*?)<\/Row>/g;
    let rowMatch;
    while ((rowMatch = rowRe.exec(sheetMatch[0])) !== null) {
        const cells = [];
        const cellRe = /<Cell[^>]*>[\s\S]*?<Data[^>]*>([\s\S]*?)<\/Data>[\s\S]*?<\/Cell>/g;
        let cellMatch;
        while ((cellMatch = cellRe.exec(rowMatch[1])) !== null) {
            cells.push(cellMatch[1].trim() || null);
        }
        rows.push(cells);
    }
    return rows;
}

function parseXmlDataset(xmlPath) {
    const xml = readFileSync(xmlPath, "utf-8");

    // Variables: variableName -> description
    const variables = {};
    for (const [name, desc] of extractSheetRows(xml, "Variables").slice(1)) {
        if (name) variables[name] = desc || name;
    }

    // Labels: variableName -> { value -> label }
    const labels = {};
    for (const [varName, val, label] of extractSheetRows(xml, "Labels")) {
        if (!varName) continue;
        if (!labels[varName]) labels[varName] = {};
        labels[varName][val] = label;
    }

    // Dataset: first row = headers, rest = respondents
    const datasetRows = extractSheetRows(xml, "Dataset");
    const headers = datasetRows[0] || [];
    const respondents = datasetRows.slice(1).map(row => {
        const record = {};
        headers.forEach((h, i) => { record[h] = row[i] ?? null; });
        return record;
    });

    return { variables, labels, headers, respondents };
}

// ─── Dataset Discovery ────────────────────────────────────────────────────────

function loadDatasets(cwd) {
    const dir = join(cwd, "datasets");
    if (!existsSync(dir)) return null;
    const files = readdirSync(dir).filter(f => f.endsWith(".xml")).map(f => join(dir, f));
    if (!files.length) return null;
    return parseXmlDataset(files[0]);
}

// ─── Statistics Helpers ───────────────────────────────────────────────────────

const isScoreVar = name => /^s_\d+$/.test(name);

function numericVals(respondents, variable, excludeNa = true) {
    return respondents
        .map(r => parseInt(r[variable], 10))
        .filter(v => !isNaN(v) && (!excludeNa || v !== 6));
}

const mean = arr => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
const median = arr => {
    if (!arr.length) return null;
    const s = [...arr].sort((a, b) => a - b);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const mode = arr => {
    if (!arr.length) return null;
    const f = {};
    arr.forEach(v => (f[v] = (f[v] || 0) + 1));
    return +Object.entries(f).sort((a, b) => b[1] - a[1])[0][0];
};
const stdDev = arr => {
    if (arr.length < 2) return 0;
    const m = mean(arr);
    return Math.sqrt(arr.reduce((s, v) => s + (v - m) ** 2, 0) / arr.length);
};
const dist = (arr, min = 1, max = 5) => {
    const c = {};
    for (let i = min; i <= max; i++) c[i] = 0;
    arr.forEach(v => { if (v in c) c[v]++; });
    return c;
};

// ─── ASCII Bar Chart ──────────────────────────────────────────────────────────

function barChart(title, counts, labelMap, total) {
    const BAR = 28;
    const maxVal = Math.max(...Object.values(counts), 1);
    let out = `📊 ${title}\n${"─".repeat(58)}\n`;
    for (const [key, count] of Object.entries(counts)) {
        const label = labelMap?.[key] || `Score ${key}`;
        const pct = total > 0 ? Math.round((count / total) * 100) : 0;
        const bar = "█".repeat(Math.round((count / maxVal) * BAR));
        out += `${String(key).padStart(2)} │ ${bar.padEnd(BAR)} ${count} (${pct}%)\n`;
        out += `   │ ${label}\n`;
    }
    out += `${"─".repeat(58)}\n   n = ${total} valid responses\n`;
    return out;
}

// ─── Extension ───────────────────────────────────────────────────────────────

const session = await joinSession({
    hooks: {
        onSessionStart: async () => {
            await session.log("📊 Survey Indsight ready — use survey_* tools to explore the data");
        },
    },
    tools: [
        // ── survey_variables ──────────────────────────────────────────────
        {
            name: "survey_variables",
            description:
                "List all survey questions/variables with their names and descriptions. Use this first to discover what is in the dataset.",
            parameters: { type: "object", properties: {} },
            skipPermission: true,
            handler: async (_args, inv) => {
                const data = loadDatasets(inv.cwd ?? process.cwd());
                if (!data) return "❌ No XML dataset found in ./datasets/";
                const { variables, respondents } = data;
                let out = `Survey dataset — ${respondents.length} respondents, ${Object.keys(variables).length} variables\n\n`;
                out += "Variable       Description\n" + "─".repeat(60) + "\n";
                for (const [name, desc] of Object.entries(variables)) {
                    out += `${name.padEnd(15)} ${desc}\n`;
                }
                return out;
            },
        },

        // ── survey_summary ────────────────────────────────────────────────
        {
            name: "survey_summary",
            description:
                "Statistical summary of survey results. Shows mean, median, mode and std dev per question. " +
                "Score scale: 1=Don't care, 2=Not important, 3=Important, 4=Very important, 5=Can't live without, 6=N/A (excluded from stats). " +
                "If 'variable' is provided, shows a detailed breakdown with bar chart for that question.",
            parameters: {
                type: "object",
                properties: {
                    variable: {
                        type: "string",
                        description: "Variable name (e.g. 's_27'). Omit to summarise all score questions.",
                    },
                    sort_by: {
                        type: "string",
                        enum: ["mean", "median", "name"],
                        description: "Sort order for the overview table. Default: mean (descending).",
                    },
                },
            },
            skipPermission: true,
            handler: async (args, inv) => {
                const data = loadDatasets(inv.cwd ?? process.cwd());
                if (!data) return "❌ No XML dataset found in ./datasets/";
                const { variables, labels, respondents } = data;

                const vars = args.variable ? [args.variable] : Object.keys(variables).filter(isScoreVar);
                if (args.variable && !variables[args.variable]) return `Unknown variable: ${args.variable}`;

                const rows = vars.map(v => {
                    const vals = numericVals(respondents, v);
                    return { v, desc: variables[v] || v, mean: mean(vals), median: median(vals), mode: mode(vals), sd: stdDev(vals), n: vals.length };
                }).filter(r => r.n > 0);

                const sortBy = args.sort_by ?? "mean";
                if (sortBy === "mean") rows.sort((a, b) => b.mean - a.mean);
                else if (sortBy === "median") rows.sort((a, b) => b.median - a.median);
                else rows.sort((a, b) => a.v.localeCompare(b.v));

                if (args.variable && rows.length === 1) {
                    const r = rows[0];
                    const allVals = numericVals(respondents, args.variable, false);
                    const validVals = allVals.filter(v => v !== 6);
                    const naCount = allVals.length - validVals.length;
                    let out = `📋 ${r.desc}\n${"─".repeat(58)}\n`;
                    out += `Mean   : ${r.mean.toFixed(2)}\n`;
                    out += `Median : ${r.median}\n`;
                    out += `Mode   : ${r.mode}\n`;
                    out += `Std Dev: ${r.sd.toFixed(2)}\n`;
                    out += `N      : ${r.n} valid, ${naCount} N/A\n\n`;
                    out += barChart(r.desc, dist(validVals), labels[args.variable], r.n);
                    return out;
                }

                let out = `Survey Summary — ${respondents.length} respondents (sorted by ${sortBy})\n\n`;
                out += `${"Var".padEnd(8)} ${"Mean".padEnd(6)} ${"Med".padEnd(5)} ${"Mod".padEnd(5)} ${"SD".padEnd(5)} N    Description\n`;
                out += "─".repeat(80) + "\n";
                for (const r of rows) {
                    out += `${r.v.padEnd(8)} ${r.mean.toFixed(2).padEnd(6)} ${String(r.median).padEnd(5)} ${String(r.mode).padEnd(5)} ${r.sd.toFixed(2).padEnd(5)} ${String(r.n).padEnd(5)} ${r.desc}\n`;
                }
                return out;
            },
        },

        // ── survey_graph ──────────────────────────────────────────────────
        {
            name: "survey_graph",
            description:
                "Show ASCII bar charts of score distributions for one or more survey questions. " +
                "Useful for visually comparing how the team rated different topics.",
            parameters: {
                type: "object",
                properties: {
                    variables: {
                        type: "array",
                        items: { type: "string" },
                        description: "List of variable names to graph. If omitted, graphs all score questions.",
                    },
                    exclude_na: {
                        type: "boolean",
                        description: "Exclude score 6 (N/A) from charts. Default: true.",
                    },
                },
            },
            skipPermission: true,
            handler: async (args, inv) => {
                const data = loadDatasets(inv.cwd ?? process.cwd());
                if (!data) return "❌ No XML dataset found in ./datasets/";
                const { variables, labels, respondents } = data;

                const excludeNa = args.exclude_na !== false;
                const maxScore = excludeNa ? 5 : 6;
                const vars = args.variables?.length
                    ? args.variables
                    : Object.keys(variables).filter(isScoreVar);

                let out = "";
                for (const v of vars) {
                    const vals = numericVals(respondents, v, excludeNa);
                    if (!vals.length) continue;
                    out += barChart(variables[v] || v, dist(vals, 1, maxScore), labels[v], vals.length) + "\n";
                }
                return out || "No data to display.";
            },
        },

        // ── survey_query ──────────────────────────────────────────────────
        {
            name: "survey_query",
            description:
                "Query individual respondent data. Filter by respondent email, question variable, and/or score range. " +
                "Returns full response details for matching respondents.",
            parameters: {
                type: "object",
                properties: {
                    variable: {
                        type: "string",
                        description: "Filter by this variable's score (combine with min_score/max_score).",
                    },
                    min_score: { type: "number", description: "Minimum score (inclusive)." },
                    max_score: { type: "number", description: "Maximum score (inclusive)." },
                    email: { type: "string", description: "Filter to respondent(s) matching this email (partial ok)." },
                    show_comments: { type: "boolean", description: "Include free-text comments. Default: true." },
                },
            },
            skipPermission: true,
            handler: async (args, inv) => {
                const data = loadDatasets(inv.cwd ?? process.cwd());
                if (!data) return "❌ No XML dataset found in ./datasets/";
                const { variables, labels, headers, respondents } = data;

                let filtered = respondents;
                if (args.email) {
                    const q = args.email.toLowerCase();
                    filtered = filtered.filter(r => r.email?.toLowerCase().includes(q));
                }
                if (args.variable) {
                    filtered = filtered.filter(r => {
                        const v = parseInt(r[args.variable], 10);
                        if (isNaN(v)) return false;
                        if (args.min_score !== undefined && v < args.min_score) return false;
                        if (args.max_score !== undefined && v > args.max_score) return false;
                        return true;
                    });
                }

                if (!filtered.length) return "No respondents match the filter.";

                const scoreVars = headers.filter(isScoreVar);
                const showComments = args.show_comments !== false;
                let out = `${filtered.length} respondent(s) found\n\n`;

                for (const r of filtered) {
                    out += `👤 ${r.email ?? "(no email)"}\n`;
                    for (const v of scoreVars) {
                        const score = r[v];
                        if (score === null || score === undefined || score === "") continue;
                        const lbl = labels[v]?.[score] ?? "";
                        out += `  ${v.padEnd(6)} ${score}  ${lbl.padEnd(26)} ${variables[v] ?? v}\n`;
                    }
                    if (showComments && r.s_10) out += `  💬 ${r.s_10}\n`;
                    out += "\n";
                }
                return out;
            },
        },

        // ── survey_outliers ───────────────────────────────────────────────
        {
            name: "survey_outliers",
            description:
                "Detect outlier respondents whose scores deviate significantly from the group average (z-score). " +
                "Also flags straight-liners who gave the same score to every question.",
            parameters: {
                type: "object",
                properties: {
                    z_threshold: {
                        type: "number",
                        description: "Z-score threshold to flag a response as unusual. Default: 1.5.",
                    },
                    variable: {
                        type: "string",
                        description: "Focus on a specific variable. Omit to check all score questions.",
                    },
                },
            },
            skipPermission: true,
            handler: async (args, inv) => {
                const data = loadDatasets(inv.cwd ?? process.cwd());
                if (!data) return "❌ No XML dataset found in ./datasets/";
                const { variables, respondents } = data;

                const zThr = args.z_threshold ?? 1.5;
                const scoreVars = args.variable
                    ? [args.variable]
                    : Object.keys(variables).filter(isScoreVar);

                // Pre-compute per-variable stats
                const stats = Object.fromEntries(
                    scoreVars.map(v => {
                        const vals = numericVals(respondents, v);
                        return [v, { mean: mean(vals) ?? 0, sd: stdDev(vals) }];
                    })
                );

                const outliers = respondents.map(r => {
                    const email = r.email ?? "(no email)";
                    const flags = [];
                    const allScores = [];

                    for (const v of scoreVars) {
                        const score = parseInt(r[v], 10);
                        if (isNaN(score) || score === 6) continue;
                        allScores.push(score);
                        const { mean: m, sd } = stats[v];
                        if (sd > 0) {
                            const z = Math.abs((score - m) / sd);
                            if (z >= zThr) {
                                flags.push({ v, score, z: z.toFixed(2), dir: score > m ? "HIGH ↑" : "LOW ↓", desc: variables[v] ?? v });
                            }
                        }
                    }

                    const uniqueScores = new Set(allScores);
                    const isStraightLiner = allScores.length >= 3 && uniqueScores.size === 1;
                    return { email, flags, isStraightLiner, allScores };
                }).filter(o => o.flags.length > 0 || o.isStraightLiner);

                if (!outliers.length) {
                    return `✅ No outliers found at z-threshold=${zThr}. All responses look normal.`;
                }

                let out = `🔍 Outlier Detection  (z-threshold: ${zThr})\n${"─".repeat(60)}\n\n`;
                for (const o of outliers) {
                    out += `👤 ${o.email}\n`;
                    if (o.isStraightLiner) {
                        out += `  ⚠️  Straight-liner — every score = ${o.allScores[0]}\n`;
                    }
                    for (const f of o.flags) {
                        out += `  ⚠️  ${f.v}  score=${f.score}  z=${f.z}  ${f.dir}  — ${f.desc}\n`;
                    }
                    out += "\n";
                }
                return out;
            },
        },

        // ── survey_priorities ─────────────────────────────────────────────
        {
            name: "survey_priorities",
            description:
                "Rank all survey topics by average priority score. Shows top N (most wanted) and bottom N (least wanted). " +
                "N/A responses (score 6) are excluded from the calculation.",
            parameters: {
                type: "object",
                properties: {
                    top_n: { type: "number", description: "Number of top items to show. Default: 5." },
                    bottom_n: { type: "number", description: "Number of bottom items to show. Default: 5." },
                },
            },
            skipPermission: true,
            handler: async (args, inv) => {
                const data = loadDatasets(inv.cwd ?? process.cwd());
                if (!data) return "❌ No XML dataset found in ./datasets/";
                const { variables, respondents } = data;

                const ranked = Object.keys(variables)
                    .filter(isScoreVar)
                    .map(v => {
                        const vals = numericVals(respondents, v);
                        return { v, desc: variables[v] ?? v, mean: mean(vals) ?? 0, n: vals.length };
                    })
                    .sort((a, b) => b.mean - a.mean);

                const topN = args.top_n ?? 5;
                const botN = args.bottom_n ?? 5;

                function renderList(items, title) {
                    let out = `${title}\n${"─".repeat(60)}\n`;
                    items.forEach(({ v, desc, mean: m, n }, i) => {
                        const bar = "█".repeat(Math.round((m / 5) * 24));
                        out += `${String(i + 1).padStart(2)}. ${bar.padEnd(24)} ${m.toFixed(2)} (n=${n})  ${desc}\n`;
                    });
                    return out;
                }

                let out = `🏆 Survey Priorities — ${respondents.length} respondents\n\n`;
                out += renderList(ranked.slice(0, topN), `Top ${topN} — highest priority`) + "\n";
                out += renderList([...ranked].slice(-botN).reverse(), `Bottom ${botN} — lowest priority`);
                return out;
            },
        },

        // ── survey_compare ────────────────────────────────────────────────
        {
            name: "survey_compare",
            description:
                "Compare two respondents side-by-side across all questions, showing their individual scores and the difference.",
            parameters: {
                type: "object",
                properties: {
                    email1: { type: "string", description: "Email (or partial) of first respondent." },
                    email2: { type: "string", description: "Email (or partial) of second respondent." },
                },
                required: ["email1", "email2"],
            },
            skipPermission: true,
            handler: async (args, inv) => {
                const data = loadDatasets(inv.cwd ?? process.cwd());
                if (!data) return "❌ No XML dataset found in ./datasets/";
                const { variables, respondents } = data;

                const find = email => respondents.find(r => r.email?.toLowerCase().includes(email.toLowerCase()));
                const r1 = find(args.email1);
                const r2 = find(args.email2);
                if (!r1) return `Respondent not found: ${args.email1}`;
                if (!r2) return `Respondent not found: ${args.email2}`;

                const scoreVars = Object.keys(variables).filter(isScoreVar);
                let out = `Comparing ${r1.email} ↔ ${r2.email}\n`;
                out += `${"Var".padEnd(8)} ${"R1".padEnd(4)} ${"R2".padEnd(4)} Δ     Description\n`;
                out += "─".repeat(70) + "\n";

                for (const v of scoreVars) {
                    const s1 = parseInt(r1[v], 10);
                    const s2 = parseInt(r2[v], 10);
                    if (isNaN(s1) && isNaN(s2)) continue;
                    const delta = (!isNaN(s1) && !isNaN(s2)) ? s2 - s1 : "?";
                    const arrow = typeof delta === "number" ? (delta > 0 ? `+${delta}` : String(delta)) : delta;
                    out += `${v.padEnd(8)} ${String(isNaN(s1) ? "-" : s1).padEnd(4)} ${String(isNaN(s2) ? "-" : s2).padEnd(4)} ${String(arrow).padEnd(6)} ${variables[v] ?? v}\n`;
                }

                if (r1.s_10) out += `\n💬 ${r1.email}: ${r1.s_10}\n`;
                if (r2.s_10) out += `\n💬 ${r2.email}: ${r2.s_10}\n`;
                return out;
            },
        },
    ],
});
