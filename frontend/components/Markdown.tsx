"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import "katex/dist/katex.min.css";
// Same scheme ChatGPT uses for code blocks
import "highlight.js/styles/atom-one-dark.min.css";

// LLMs emit LaTeX as \(...\) / \[...\] but remark-math only parses $...$ /
// $$...$$, so normalize before rendering.
function normalizeMath(text: string): string {
  return text
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, m) => `\n$$${m}$$\n`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, m) => `$${m}$`);
}

export function Markdown({
  children,
  // The live bubble re-renders up to 60x/s while streaming — skip
  // highlighting there; finalized messages render once with colors.
  highlight = true,
}: {
  children: string;
  highlight?: boolean;
}) {
  return (
    <div className="md-body space-y-2 [&_a]:text-orange-400 [&_a]:underline [&_blockquote]:border-l-4 [&_blockquote]:border-stone-700 [&_blockquote]:pl-3 [&_blockquote]:text-stone-400 [&_code]:bg-black [&_code]:px-1 [&_code]:text-orange-300 [&_h1]:mt-3 [&_h1]:text-[1.35em] [&_h1]:font-bold [&_h1]:text-orange-400 [&_h2]:mt-3 [&_h2]:text-[1.2em] [&_h2]:font-bold [&_h2]:text-orange-400 [&_h3]:mt-2 [&_h3]:text-[1.1em] [&_h3]:font-semibold [&_h3]:text-orange-300 [&_h4]:font-semibold [&_h4]:text-orange-200 [&_hr]:border-stone-700 [&_li]:ml-5 [&_li]:leading-relaxed [&_ol]:list-decimal [&_p]:leading-relaxed [&_pre]:overflow-x-auto [&_pre]:border-2 [&_pre]:border-stone-700 [&_pre]:bg-black [&_pre]:p-3 [&_strong]:text-[1.08em] [&_strong]:font-bold [&_strong]:text-orange-400 [&_table]:border-2 [&_table]:border-stone-700 [&_td]:border [&_td]:border-stone-700 [&_td]:px-2 [&_th]:border [&_th]:border-stone-600 [&_th]:bg-stone-900 [&_th]:px-2 [&_ul]:list-disc">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={
          highlight
            ? [rehypeKatex, [rehypeHighlight, { detect: true }]]
            : [rehypeKatex]
        }
      >
        {normalizeMath(children)}
      </ReactMarkdown>
    </div>
  );
}
