async function analyzeNER() {
  const sourceText = document.getElementById("sourceText").value;
  const compareText = document.getElementById("compareText").value;

  const response = await fetch("/ner", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: sourceText, compare: compareText })
  });

  const data = await response.json();
  updateTable(data.matches);
  drawGraph(data.graph);
}

function getSelectedTypes() {
  return Array.from(document.querySelectorAll(".entityFilter:checked"))
              .map(cb => cb.value);
}

function updateTable(matches) {
  const selectedTypes = getSelectedTypes();
  const tbody = document.querySelector("#matchesTable tbody");
  tbody.innerHTML = "";

  matches
      .filter(ent => selectedTypes.includes(ent.label))
      .forEach(ent => {
          const row = document.createElement("tr");
          const cellText = document.createElement("td");
          const cellLabel = document.createElement("td");
          cellText.textContent = ent.text;
          cellLabel.textContent = ent.label;
          row.appendChild(cellText);
          row.appendChild(cellLabel);
          tbody.appendChild(row);
      });
}

function drawGraph(graphData) {
  const selectedTypes = getSelectedTypes();
  const filteredNodes = graphData.nodes.filter(n => selectedTypes.includes(n.group));
  const nodeIds = new Set(filteredNodes.map(n => n.id));
  const filteredLinks = graphData.links.filter(l => nodeIds.has(l.source) && nodeIds.has(l.target));

  const svg = d3.select("#graph");
  svg.selectAll("*").remove();
  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;

  const color = d3.scaleOrdinal(d3.schemeCategory10);

  const simulation = d3.forceSimulation(filteredNodes)
      .force("link", d3.forceLink(filteredLinks).id(d => d.id).distance(100))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(20));

  const link = svg.append("g")
      .attr("stroke", "#999")
      .attr("stroke-opacity", 0.6)
      .selectAll("line")
      .data(filteredLinks)
      .join("line")
      .attr("stroke-width", 2);

  const node = svg.append("g")
      .selectAll("g")
      .data(filteredNodes)
      .join("g")
      .call(d3.drag()
          .on("start", dragstarted)
          .on("drag", dragged)
          .on("end", dragended));

  node.append("circle")
      .attr("r", 12)
      .attr("fill", d => color(d.group));

  node.append("text")
      .text(d => d.id)
      .attr("x", 15)
      .attr("y", 4)
      .style("font-size", "12px");

  const tooltip = d3.select("body").append("div")
      .attr("class", "tooltip");

  node.on("mouseover", (event, d) => {
      tooltip.style("opacity", 1)
          .html(`Сущность: ${d.id}<br>Тип: ${d.group}`)
          .style("left", (event.pageX + 10) + "px")
          .style("top", (event.pageY + 10) + "px");
  }).on("mouseout", () => tooltip.style("opacity", 0));

  simulation.on("tick", () => {
      filteredNodes.forEach(d => {
          d.x = Math.max(20, Math.min(width - 20, d.x));
          d.y = Math.max(20, Math.min(height - 20, d.y));
      });

      link
          .attr("x1", d => d.source.x)
          .attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x)
          .attr("y2", d => d.target.y);

      node.attr("transform", d => `translate(${d.x},${d.y})`);
  });

  function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x; d.fy = d.y;
  }
  function dragged(event, d) { d.fx = event.x; d.fy = event.y; }
  function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null; d.fy = null;
  }
}

document.querySelectorAll(".entityFilter").forEach(cb => {
  cb.addEventListener("change", analyzeNER);
});
