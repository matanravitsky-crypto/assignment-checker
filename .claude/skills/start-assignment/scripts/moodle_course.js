// Explore a Moodle course from a logged-in Moodle tab (Claude in Chrome, javascript_tool), for the start-assignment skill.
// Moodle has no API, so this fetches Moodle's own pages with the user's session and reads them. It clicks nothing and
// types nothing; the only thing it writes is a file into Downloads (`download`). Paste the whole file once into
// javascript_tool (it answers "ready"), then call one function per javascript_tool call:
//
//   await __ecs.course(67024)            sections and activities: "## section" lines, then "  name <type id>" lines
//   await __ecs.assign(3438638)          one assignment's page as JSON: title, dates, intro (questions and rules)
//   await __ecs.resource(3438679)        where a "file" activity points (its pluginfile URL), nothing downloaded
//   await __ecs.download(3438679, "sheets-09-16.pdf")   save that file to Downloads under this name (no dialog)
//
// An expired session shows nginx "404 Not Found" (not a login page): the functions answer "NOT LOGGED IN"; open
// https://moodle.bgu.ac.il/moodle/my/ once in the tab (Moodle signs in again by itself) and call again.
window.__ecs = (() => {
  const text = (el) => (el ? el.innerText.replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n").trim() : "");
  const parse = async (url) => {
    const r = await fetch(url, { credentials: "same-origin" });
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(r.status + " " + url);
    return new DOMParser().parseFromString(await r.text(), "text/html");
  };
  const loggedOut = (d) => !d || !!d.querySelector('form[action*="login/index.php"], #login');
  const kind = { assign: "assign", resource: "file", page: "page", folder: "folder", forum: "forum", scorm: "scorm",
                 quiz: "quiz", url: "url", label: "label" };

  async function course(cid) {
    const d = await parse("/moodle/course/view.php?id=" + cid);
    if (loggedOut(d)) return "NOT LOGGED IN";
    const out = [];
    for (const li of d.querySelectorAll("li.section, li.activity")) {
      if (li.classList.contains("section")) {
        out.push("## " + text(li.querySelector(".sectionname, h3, .section-title")));
        continue;
      }
      const a = li.querySelector('a[href*="/mod/"]');
      const m = a && a.href.match(/\/mod\/(\w+)\/view\.php\?id=(\d+)/);
      const name = text(li.querySelector(".instancename") || li.querySelector(".activityname") || li).split("\n")[0];
      const dates = [...li.querySelectorAll('[data-region="activity-dates"] div, .activity-dates div')].map(text).join("; ");
      out.push("  " + name + (m ? ` <${kind[m[1]] || m[1]} ${m[2]}>` : "") + (dates ? "  " + dates : ""));
    }
    return out.join("\n");
  }

  async function assign(id) {
    const d = await parse("/moodle/mod/assign/view.php?id=" + id);
    if (loggedOut(d)) return "NOT LOGGED IN";
    const main = d.querySelector("[role=main]") || d.body;
    const title = text(main.querySelector("h1, h2") || d.querySelector("h1"));
    const intro = text(main.querySelector(".activity-description, #intro, .box.generalbox, .description"));
    const dates = [...main.querySelectorAll('[data-region="activity-dates"] div, .activity-dates div')].map(text);
    for (const line of text(main).split("\n"))
      if (/^(מסתיים|נפתח|תאריך הגשה|Due|Opened|Closes)\b/.test(line) && !dates.includes(line)) dates.push(line);
    return JSON.stringify({ id: String(id), title, dates, intro });
  }

  async function resource(id) {
    const r = await fetch("/moodle/mod/resource/view.php?id=" + id, { credentials: "same-origin" });
    const body = r.url.includes("pluginfile.php") ? "" : await r.text();
    const m = body.match(/https?:[^"']*pluginfile\.php[^"']*/);
    return { id: String(id), url: r.url, file: m ? m[0].replace(/&amp;/g, "&") : (r.url.includes("pluginfile.php") ? r.url : null) };
  }

  async function download(id, name) {
    if (!/^[\w\- .()]+\.pdf$/i.test(name)) throw new Error("name: a plain file name ending in .pdf");
    const r = await fetch("/moodle/mod/resource/view.php?id=" + id, { credentials: "same-origin" });
    const b = await r.blob();
    if (b.type && !/pdf|octet-stream/.test(b.type)) return { id: String(id), name, error: "not a PDF: " + b.type, url: r.url };
    const a = document.createElement("a");
    a.href = URL.createObjectURL(b);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    return { id: String(id), name, type: b.type, bytes: b.size };
  }

  return { course, assign, resource, download };
})();
"ready";
