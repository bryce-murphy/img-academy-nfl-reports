(function () {
  var list = document.querySelector(".explorer-list");
  if (!list) return;
  var stage = document.getElementById("play-stage");
  var items = Array.prototype.slice.call(list.querySelectorAll("li.play"));
  var filters = document.querySelector(".explorer-filters");
  if (!stage || !filters) return;
  document.documentElement.classList.add("js-explorer");
  filters.hidden = false;
  stage.hidden = false;

  function select(item, updateHash, fromClick) {
    items.forEach(function (i) { i.removeAttribute("aria-current"); });
    item.setAttribute("aria-current", "true");
    var large = item.querySelector("template.play-large");
    stage.innerHTML = large ? large.innerHTML : "";
    var text = item.querySelector(".play-line");
    if (!large && text) stage.textContent = text.textContent;
    if (fromClick && getComputedStyle(stage).display === "none") {
      var more = item.querySelector("details.play-more");
      if (more) more.open = true;
    }
    if (updateHash) history.replaceState(null, "", "#" + item.id);
  }

  function matches(item, filter) {
    var tag = item.getAttribute("data-tag");
    if (filter === "impact") return item.classList.contains("impact");
    if (filter === "helped") return tag === "big" || tag === "helped";
    if (filter === "hurt") return tag === "hurt";
    return true;
  }

  filters.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-filter]");
    if (!button) return;
    filters.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); });
    items.forEach(function (i) { i.hidden = !matches(i, button.getAttribute("data-filter")); });
    var current = items.find(function (i) { return i.getAttribute("aria-current") === "true"; });
    if (!current || current.hidden) {
      var visible = items.find(function (i) { return !i.hidden; });
      if (visible) {
        select(visible, false);
      } else {
        items.forEach(function (i) { i.removeAttribute("aria-current"); });
        stage.innerHTML = "";
      }
    }
  });

  list.addEventListener("click", function (event) {
    var pick = event.target.closest(".play-pick");
    if (pick) select(pick.closest("li.play"), true, true);
  });

  var initial = (location.hash && items.find(function (i) { return i.id === location.hash.slice(1); })) || items[0];
  if (initial) select(initial, false);
})();
