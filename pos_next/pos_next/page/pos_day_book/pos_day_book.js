// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.provide("pos_next.day_book");

frappe.pages["pos-day-book"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("POS Day Book"),
		single_column: true,
	});

	wrapper.day_book = new pos_next.day_book.POSDayBook(page);
};

frappe.pages["pos-day-book"].on_page_show = function (wrapper) {
	const day_book = wrapper.day_book;
	if (!day_book) return;

	// on_page_load already loaded the first set — only reload when the owner
	// navigates back to a page that has been sitting in the background.
	if (day_book.first_show) {
		day_book.first_show = false;
		return;
	}

	day_book.refresh();
};

pos_next.day_book.PRESETS = [
	{ key: "today", label: __("Today") },
	{ key: "yesterday", label: __("Yesterday") },
	{ key: "this_week", label: __("This Week") },
	{ key: "this_month", label: __("This Month") },
	{ key: "last_month", label: __("Last Month") },
	{ key: "this_year", label: __("This Year") },
];

pos_next.day_book.POSDayBook = class POSDayBook {
	constructor(page) {
		this.page = page;
		this.controls = {};
		this.charts = {};
		this.request_id = 0;
		this.first_show = true;

		this.make();
		this.refresh();
	}

	make() {
		this.$container = $('<div class="pos-day-book"></div>').appendTo(this.page.main);

		this.make_actions();
		this.make_filters();

		this.$body = $('<div class="pdb-body"></div>').appendTo(this.$container);
		this.$kpis = $('<div class="pdb-kpi-grid"></div>').appendTo(this.$body);
		this.$charts = $('<div class="pdb-chart-grid"></div>').appendTo(this.$body);
		this.$analysis = $('<div class="pdb-chart-grid pdb-analysis"></div>').appendTo(this.$body);
		this.$expenses = $('<div class="pdb-card pdb-expenses"></div>').appendTo(this.$body);
		this.$ledger = $('<div class="pdb-card pdb-ledger"></div>').appendTo(this.$body);
		this.$shifts = $('<div class="pdb-card pdb-shifts"></div>').appendTo(this.$body);
	}

	make_actions() {
		this.page.set_primary_action(
			__("Refresh"),
			() => this.refresh(),
			"refresh"
		);

		this.page.add_menu_item(__("Export Day Book (CSV)"), () => this.export_ledger());
		this.page.add_menu_item(__("Export POS Expenses (CSV)"), () => this.export_expenses());
		this.page.add_menu_item(__("Print Dashboard"), () => window.print());
	}

	// ---------------------------------------------------------------- filters

	make_filters() {
		const $card = $(`
			<div class="pdb-card pdb-filters">
				<div class="pdb-filter-grid"></div>
				<div class="pdb-preset-row"></div>
			</div>
		`).appendTo(this.$container);

		const $grid = $card.find(".pdb-filter-grid");
		const refresh = frappe.utils.debounce(() => this.refresh(), 250);

		const fields = [
			{
				fieldtype: "Date",
				fieldname: "from_date",
				label: __("From Date"),
				default: frappe.datetime.get_today(),
			},
			{
				fieldtype: "Date",
				fieldname: "to_date",
				label: __("To Date"),
				default: frappe.datetime.get_today(),
			},
			{
				fieldtype: "Link",
				fieldname: "company",
				label: __("Company"),
				options: "Company",
				default: frappe.defaults.get_user_default("company"),
			},
			{
				fieldtype: "Link",
				fieldname: "cost_center",
				label: __("Cost Center"),
				options: "Cost Center",
				get_query: () => {
					const company = this.get_value("company");
					return { filters: company ? { company: company } : {} };
				},
			},
			{
				fieldtype: "Link",
				fieldname: "pos_profile",
				label: __("POS Profile"),
				options: "POS Profile",
			},
			{
				fieldtype: "Link",
				fieldname: "cashier",
				label: __("Cashier"),
				options: "User",
			},
			{
				fieldtype: "Link",
				fieldname: "shift",
				label: __("Shift"),
				options: "POS Closing Shift",
			},
			{
				fieldtype: "Link",
				fieldname: "mode_of_payment",
				label: __("Mode of Payment"),
				options: "Mode of Payment",
			},
			{
				fieldtype: "Check",
				fieldname: "pos_only",
				label: __("POS Transactions Only"),
				default: 1,
			},
		];

		fields.forEach((df) => {
			const $slot = $('<div class="pdb-filter"></div>').appendTo($grid);

			this.controls[df.fieldname] = frappe.ui.form.make_control({
				df: Object.assign({}, df, {
					onchange: () => {
						if (df.fieldname === "from_date" || df.fieldname === "to_date") {
							this.sync_active_preset();
						}
						refresh();
					},
				}),
				parent: $slot,
				render_input: true,
			});

			if (df.default !== undefined) {
				this.controls[df.fieldname].set_value(df.default);
			}
		});

		this.make_presets($card.find(".pdb-preset-row"));
	}

	make_presets($row) {
		pos_next.day_book.PRESETS.forEach((preset) => {
			$(`<button class="btn btn-xs pdb-preset" data-preset="${preset.key}">${preset.label}</button>`)
				.appendTo($row)
				.on("click", () => this.apply_preset(preset.key));
		});

		this.apply_preset("today", true);
	}

	preset_range(key) {
		// frappe.datetime.month_start() and friends take no argument and return an
		// ISO datetime, so build the ranges with moment and keep them date-only.
		const day = (m) => m.format("YYYY-MM-DD");

		switch (key) {
			case "yesterday": {
				const d = day(moment().subtract(1, "days"));
				return { from_date: d, to_date: d };
			}
			case "this_week":
				return {
					from_date: day(moment().startOf("week")),
					to_date: day(moment().endOf("week")),
				};
			case "this_month":
				return {
					from_date: day(moment().startOf("month")),
					to_date: day(moment().endOf("month")),
				};
			case "last_month": {
				const m = moment().subtract(1, "months");
				return {
					from_date: day(m.clone().startOf("month")),
					to_date: day(m.clone().endOf("month")),
				};
			}
			case "this_year":
				return {
					from_date: day(moment().startOf("year")),
					to_date: day(moment().endOf("year")),
				};
			default: {
				const d = day(moment());
				return { from_date: d, to_date: d };
			}
		}
	}

	apply_preset(key, silent) {
		const range = this.preset_range(key);

		this.controls.from_date.set_value(range.from_date);
		this.controls.to_date.set_value(range.to_date);
		this.sync_active_preset();

		if (!silent) {
			this.refresh();
		}
	}

	sync_active_preset() {
		// Derive the highlight from the dates themselves. The Date control fires
		// its change event asynchronously, so a "currently applying" flag would
		// already be cleared by the time the handler ran — and this way, typing a
		// range by hand that happens to be a preset lights that preset up too.
		const from_date = this.get_value("from_date");
		const to_date = this.get_value("to_date");

		const match = pos_next.day_book.PRESETS.find((preset) => {
			const range = this.preset_range(preset.key);
			return range.from_date === from_date && range.to_date === to_date;
		});

		this.$container.find(".pdb-preset").removeClass("active");
		if (match) {
			this.$container.find(`.pdb-preset[data-preset="${match.key}"]`).addClass("active");
		}
	}

	get_value(fieldname) {
		const control = this.controls[fieldname];
		return control ? control.get_value() : null;
	}

	get_filters() {
		const filters = {};
		Object.keys(this.controls).forEach((fieldname) => {
			const value = this.get_value(fieldname);
			if (value !== null && value !== undefined && value !== "") {
				filters[fieldname] = value;
			}
		});
		// A cleared checkbox must reach the server as 0, not go missing.
		filters.pos_only = cint(this.get_value("pos_only"));
		return filters;
	}

	// ---------------------------------------------------------------- refresh

	refresh() {
		if (!this.controls.from_date) return;

		const request_id = ++this.request_id;

		frappe
			.call({
				method: "pos_next.api.dashboard.get_day_book",
				args: { filters: this.get_filters() },
				freeze: true,
				freeze_message: __("Crunching the numbers..."),
			})
			.then((r) => {
				// Filters can change faster than the server replies — drop stale ones.
				if (request_id !== this.request_id || !r.message) return;
				this.render(r.message);
			});
	}

	render(data) {
		this.data = data;
		this.currency = data.meta.currency;

		this.render_kpis(data.kpis);
		this.render_charts(data);
		this.render_analysis(data);
		this.render_expenses(data.expenses);
		this.render_ledger(data.ledger);
		this.render_shifts(data.shifts);
	}

	// ------------------------------------------------------------------- KPIs

	render_kpis(kpis) {
		this.$kpis.empty();

		kpis.forEach((kpi) => {
			const $tile = $(`
				<div class="pdb-kpi pdb-tone-${kpi.tone}" data-key="${kpi.key}">
					<div class="pdb-kpi-label">${frappe.utils.escape_html(kpi.label)}</div>
					<div class="pdb-kpi-value">${this.format_value(kpi.value, kpi.fieldtype)}</div>
					<div class="pdb-kpi-delta">${this.delta_html(kpi)}</div>
				</div>
			`).appendTo(this.$kpis);

			$tile.on("click", () => this.drill_down(kpi.key));
		});
	}

	delta_html(kpi) {
		if (kpi.delta_pct === null || kpi.delta_pct === undefined) {
			return `<span class="pdb-delta-flat">${__("No prior period")}</span>`;
		}

		const up = kpi.delta_pct >= 0;
		const cls = up ? "pdb-delta-up" : "pdb-delta-down";
		const arrow = up ? "&#9650;" : "&#9660;";

		return `<span class="${cls}">${arrow} ${Math.abs(kpi.delta_pct).toFixed(1)}%</span>
			<span class="pdb-delta-prev">${__("vs")} ${this.format_value(
				kpi.prev_value,
				kpi.fieldtype
			)}</span>`;
	}

	format_value(value, fieldtype) {
		if (fieldtype === "Currency") {
			return format_currency(value, this.currency);
		}
		if (fieldtype === "Int") {
			return format_number(value, null, 0);
		}
		return format_number(value, null, 2);
	}

	drill_down(key) {
		const filters = this.get_filters();
		const route_filters = {
			docstatus: 1,
			posting_date: ["between", [filters.from_date, filters.to_date]],
		};

		if (filters.pos_only) route_filters.is_pos = 1;
		if (filters.company) route_filters.company = filters.company;
		if (filters.cost_center) route_filters.cost_center = filters.cost_center;
		if (filters.pos_profile) route_filters.pos_profile = filters.pos_profile;
		if (filters.cashier) route_filters.owner = filters.cashier;

		if (key === "returns_amount" || key === "return_count") {
			route_filters.is_return = 1;
		} else if (key === "gross_sales" || key === "invoice_count") {
			route_filters.is_return = 0;
		} else if (key === "outstanding") {
			route_filters.status = ["in", ["Unpaid", "Overdue", "Partly Paid"]];
		} else if (key === "purchase") {
			frappe.set_route("List", "Purchase Invoice", {
				docstatus: 1,
				posting_date: ["between", [filters.from_date, filters.to_date]],
			});
			return;
		} else if (key === "pos_expense") {
			frappe.set_route("List", "Journal Entry", {
				docstatus: 1,
				custom_created_from_pos: 1,
				posting_date: ["between", [filters.from_date, filters.to_date]],
			});
			return;
		}

		frappe.set_route("List", "Sales Invoice", route_filters);
	}

	// ----------------------------------------------------------------- charts

	render_charts(data) {
		this.$charts.empty();
		this.charts = {};

		const has_sales = data.kpis.some((k) => k.key === "net_sales" && k.value) || data.ledger.rows.length;

		if (!has_sales) {
			this.$charts.append(`
				<div class="pdb-card pdb-empty pdb-span-2">
					<div class="pdb-empty-title">${__("No transactions for the selected filters")}</div>
					<div class="pdb-empty-hint">${__("Try widening the date range or clearing a filter.")}</div>
				</div>
			`);
			return;
		}

		this.make_chart("trend", __("Sales, Returns & Net"), "pdb-span-2", {
			data: {
				labels: data.trend.labels,
				datasets: data.trend.datasets,
			},
			type: "axis-mixed",
			height: 280,
			colors: ["#28a745", "#dc3545", "#2490ef"],
			axisOptions: { xIsSeries: true, shortenYAxisNumbers: 1 },
			lineOptions: { hideDots: data.trend.labels.length > 40 ? 1 : 0, regionFill: 0 },
			tooltipOptions: {
				formatTooltipY: (value) => format_currency(value, this.currency),
			},
		});

		this.make_chart("payments", __("Payment Split"), "", {
			data: {
				labels: data.payments.map((p) => p.label),
				datasets: [{ values: data.payments.map((p) => p.value) }],
			},
			type: "donut",
			height: 260,
			maxSlices: 8,
			tooltipOptions: {
				formatTooltipY: (value) => format_currency(value, this.currency),
			},
		});

		this.make_chart("cashiers", __("Sales by Cashier"), "", {
			data: {
				labels: data.cashiers.map((c) => c.label),
				datasets: [{ values: data.cashiers.map((c) => c.value) }],
			},
			type: "bar",
			height: 260,
			colors: ["#2490ef"],
			axisOptions: { shortenYAxisNumbers: 1 },
			tooltipOptions: {
				formatTooltipY: (value) => format_currency(value, this.currency),
			},
		});

		this.make_chart("top_items", __("Top Items"), "", {
			data: {
				labels: data.top_items.slice(0, 10).map((i) => i.label),
				datasets: [{ values: data.top_items.slice(0, 10).map((i) => i.value) }],
			},
			type: "bar",
			height: 280,
			colors: ["#7c3aed"],
			axisOptions: { shortenYAxisNumbers: 1 },
			tooltipOptions: {
				formatTooltipY: (value) => format_currency(value, this.currency),
			},
		});

		this.make_chart("top_groups", __("Top Item Groups"), "", {
			data: {
				labels: data.top_groups.slice(0, 10).map((g) => g.label),
				datasets: [{ values: data.top_groups.slice(0, 10).map((g) => g.value) }],
			},
			type: "pie",
			height: 280,
			maxSlices: 8,
			tooltipOptions: {
				formatTooltipY: (value) => format_currency(value, this.currency),
			},
		});
	}

	make_chart(key, title, extra_class, options) {
		const has_values = (options.data.datasets || []).some((ds) =>
			(ds.values || []).some((v) => v)
		);

		const $card = $(`
			<div class="pdb-card pdb-chart-card ${extra_class}">
				<div class="pdb-section-title">${title}</div>
				<div class="pdb-chart"></div>
			</div>
		`).appendTo(this.$charts);

		const $chart = $card.find(".pdb-chart");

		if (!has_values) {
			$chart.html(`<div class="pdb-empty-inline">${__("No data")}</div>`);
			return;
		}

		// frappe-charts holds on to its container, so always draw into a fresh one.
		this.charts[key] = new frappe.Chart($chart.get(0), options);
	}

	// ----------------------------------------------------------------- ledger

	render_ledger(ledger) {
		this.$ledger.empty();

		const note = ledger.has_more
			? `<span class="pdb-section-note">${__("Showing the latest {0} invoices", [
					ledger.limit,
			  ])}</span>`
			: "";

		this.$ledger.append(`
			<div class="pdb-section-title">${__("Day Book")} ${note}</div>
			<div class="pdb-datatable"></div>
		`);

		const $table = this.$ledger.find(".pdb-datatable");

		if (!ledger.rows.length) {
			$table.html(`<div class="pdb-empty-inline">${__("No transactions for the selected filters")}</div>`);
			return;
		}

		const currency = this.currency;
		const money = (value) => format_currency(value, currency);

		const columns = [
			{ name: __("Date"), id: "posting_date", width: 100 },
			{ name: __("Time"), id: "posting_time", width: 80 },
			{
				name: __("Invoice"),
				id: "name",
				width: 170,
				format: (value, row, column, doc) => {
					const label = frappe.utils.escape_html(value || "");
					const badge = doc.is_return
						? ` <span class="pdb-badge pdb-badge-return">${__("Return")}</span>`
						: "";
					return `<a href="/app/sales-invoice/${encodeURIComponent(value)}">${label}</a>${badge}`;
				},
			},
			{ name: __("Customer"), id: "customer_name", width: 160 },
			{ name: __("Cashier"), id: "cashier", width: 130 },
			{ name: __("Cost Center"), id: "cost_center", width: 140 },
			{ name: __("POS Profile"), id: "pos_profile", width: 130 },
			{ name: __("Payment"), id: "modes", width: 140 },
			{ name: __("Qty"), id: "total_qty", width: 70, align: "right" },
			{
				name: __("Total"),
				id: "base_grand_total",
				width: 120,
				align: "right",
				format: money,
			},
			{
				name: __("Discount"),
				id: "base_discount_amount",
				width: 110,
				align: "right",
				format: money,
			},
			{
				name: __("Tax"),
				id: "base_total_taxes_and_charges",
				width: 110,
				align: "right",
				format: money,
			},
			{ name: __("Taxable"), id: "base_net_total", width: 120, align: "right", format: money },
			{
				name: __("Outstanding"),
				id: "outstanding_amount",
				width: 120,
				align: "right",
				format: money,
			},
		];

		if (this.ledger_table) {
			this.ledger_table.destroy && this.ledger_table.destroy();
			this.ledger_table = null;
		}

		this.ledger_table = new frappe.DataTable($table.get(0), {
			columns: columns,
			data: ledger.rows,
			// "fluid" squeezes 14 columns until the currency values ellipsize;
			// "fixed" keeps the declared widths and scrolls sideways instead.
			layout: "fixed",
			inlineFilters: true,
			noDataMessage: __("No transactions"),
			checkboxColumn: false,
			serialNoColumn: false,
			dynamicRowHeight: false,
		});

		this.render_ledger_totals(ledger.rows);
	}

	render_ledger_totals(rows) {
		const sum = (field) => rows.reduce((total, row) => total + flt(row[field]), 0);

		$(`
			<div class="pdb-totals">
				<span>${__("Rows")}: <b>${rows.length}</b></span>
				<span>${__("Total")}: <b>${format_currency(sum("base_grand_total"), this.currency)}</b></span>
				<span>${__("Discount")}: <b>${format_currency(
					sum("base_discount_amount"),
					this.currency
				)}</b></span>
				<span>${__("Tax")}: <b>${format_currency(
					sum("base_total_taxes_and_charges"),
					this.currency
				)}</b></span>
				<span>${__("Taxable")}: <b>${format_currency(sum("base_net_total"), this.currency)}</b></span>
				<span>${__("Outstanding")}: <b>${format_currency(
					sum("outstanding_amount"),
					this.currency
				)}</b></span>
			</div>
		`).appendTo(this.$ledger);
	}

	// ------------------------------------------------------------ shift table

	// ------------------------------------------------------------ table helper

	/**
	 * Render a simple read-only table into `$el`.
	 *
	 * Each column is {label, key, align, html}. `html` is an optional
	 * (value, row) => string that returns already-escaped markup; without it the
	 * value is escaped and printed as-is.
	 */
	render_table($el, opts) {
		$el.empty();

		const note = opts.note ? `<span class="pdb-section-note">${opts.note}</span>` : "";
		$el.append(`<div class="pdb-section-title">${opts.title} ${note}</div>`);

		if (!opts.rows.length) {
			$el.append(`<div class="pdb-empty-inline">${opts.empty}</div>`);
			return;
		}

		const cell = (column, row) => {
			const value = row[column.key];
			return column.html
				? column.html(value, row)
				: frappe.utils.escape_html(value === null || value === undefined ? "" : String(value));
		};

		const css = (c) =>
			[c.align === "right" ? "text-right" : "", c.truncate ? "pdb-truncate" : ""]
				.filter(Boolean)
				.join(" ");

		const head = opts.columns.map((c) => `<th class="${css(c)}">${c.label}</th>`).join("");

		const body = opts.rows
			.map(
				(row) =>
					"<tr>" +
					opts.columns
						.map((c) => {
							const title = c.truncate
								? ` title="${frappe.utils.escape_html(String(row[c.key] ?? ""))}"`
								: "";
							return `<td class="${css(c)}"${title}>${cell(c, row)}</td>`;
						})
						.join("") +
					"</tr>"
			)
			.join("");

		$el.append(`
			<div class="pdb-table-scroll">
				<table class="table table-sm pdb-table">
					<thead><tr>${head}</tr></thead>
					<tbody>${body}</tbody>
				</table>
			</div>
		`);
	}

	link_cell(doctype, name, label) {
		const route = frappe.router.slug(doctype);
		return `<a href="/app/${route}/${encodeURIComponent(name)}">${frappe.utils.escape_html(
			label || name
		)}</a>`;
	}

	share_cell(percentage) {
		// A thin bar behind the number makes the ranking readable at a glance.
		const width = Math.max(0, Math.min(100, flt(percentage)));
		return `<div class="pdb-share">
			<div class="pdb-share-bar" style="width: ${width}%"></div>
			<span class="pdb-share-text">${flt(percentage, 2)}%</span>
		</div>`;
	}

	// ------------------------------------------------- top items / item groups

	render_analysis(data) {
		this.$analysis.empty();

		const money = (value) => format_currency(value, this.currency);
		const qty = (value) => format_number(value, null, 2);

		const $items = $('<div class="pdb-card"></div>').appendTo(this.$analysis);
		this.render_table($items, {
			title: __("Top Selling Items"),
			note: __("share of period sales"),
			empty: __("No items sold in this period"),
			rows: data.top_items,
			columns: [
				{
					label: __("Item"),
					key: "label",
					truncate: true,
					html: (value, row) => this.link_cell("Item", row.item_code, value),
				},
				{ label: __("Item Group"), key: "item_group", truncate: true },
				{ label: __("Qty"), key: "qty", align: "right", html: qty },
				{ label: __("Sales Value"), key: "value", align: "right", html: money },
				{
					label: __("Contribution"),
					key: "percentage",
					align: "right",
					html: (value) => this.share_cell(value),
				},
			],
		});

		const $groups = $('<div class="pdb-card"></div>').appendTo(this.$analysis);
		this.render_table($groups, {
			title: __("Top Selling Item Groups"),
			note: __("share of period sales"),
			empty: __("No items sold in this period"),
			rows: data.top_groups,
			columns: [
				{
					label: __("Item Group"),
					key: "label",
					truncate: true,
					html: (value) => this.link_cell("Item Group", value, value),
				},
				{ label: __("Items"), key: "item_count", align: "right" },
				{ label: __("Qty"), key: "qty", align: "right", html: qty },
				{ label: __("Sales Value"), key: "value", align: "right", html: money },
				{
					label: __("Contribution"),
					key: "percentage",
					align: "right",
					html: (value) => this.share_cell(value),
				},
			],
		});
	}

	// ----------------------------------------------------------- POS expenses

	render_expenses(expenses) {
		this.$expenses.empty();

		const money = (value) => format_currency(value, this.currency);

		this.$expenses.append(`
			<div class="pdb-section-title">
				${__("POS Expenses")}
				<span class="pdb-section-note">${__("Journal Entries raised from the POS")} &middot;
					${__("Total")}: <b>${money(expenses.total)}</b></span>
			</div>
		`);

		if (!expenses.rows.rows.length) {
			this.$expenses.append(
				`<div class="pdb-empty-inline">${__("No POS expenses in this period")}</div>`
			);
			return;
		}

		const $split = $('<div class="pdb-expense-split"></div>').appendTo(this.$expenses);
		const $chart = $('<div class="pdb-expense-chart"></div>').appendTo($split);
		const $accounts = $('<div class="pdb-expense-accounts"></div>').appendTo($split);

		this.charts.expenses = new frappe.Chart($chart.get(0), {
			data: {
				labels: expenses.by_account.slice(0, 10).map((a) => a.label),
				datasets: [{ values: expenses.by_account.slice(0, 10).map((a) => a.value) }],
			},
			type: "bar",
			height: 260,
			colors: ["#e86c13"],
			axisOptions: { shortenYAxisNumbers: 1 },
			tooltipOptions: { formatTooltipY: (value) => money(value) },
		});

		this.render_table($accounts, {
			title: __("By Expense Account"),
			empty: __("No expense accounts"),
			rows: expenses.by_account,
			columns: [
				{
					label: __("Account"),
					key: "label",
					html: (value) => this.link_cell("Account", value, value),
				},
				{ label: __("Entries"), key: "entry_count", align: "right" },
				{ label: __("Amount"), key: "value", align: "right", html: money },
				{
					label: __("Share"),
					key: "percentage",
					align: "right",
					html: (value) => this.share_cell(value),
				},
			],
		});

		const $entries = $('<div class="pdb-expense-entries"></div>').appendTo(this.$expenses);
		this.render_table($entries, {
			title: __("Expense Entries"),
			note: expenses.rows.has_more
				? __("Showing the latest {0} entries", [expenses.rows.limit])
				: "",
			empty: __("No POS expenses in this period"),
			rows: expenses.rows.rows,
			columns: [
				{
					label: __("Date"),
					key: "posting_date",
					html: (value) => frappe.datetime.str_to_user(value),
				},
				{
					label: __("Journal Entry"),
					key: "name",
					html: (value) => this.link_cell("Journal Entry", value, value),
				},
				{ label: __("Expense Account"), key: "accounts", truncate: true },
				{ label: __("Remark"), key: "user_remark", truncate: true },
				{ label: __("POS Profile"), key: "pos_profile" },
				{
					label: __("Shift"),
					key: "shift",
					html: (value) =>
						value ? this.link_cell("POS Opening Shift", value, value) : "",
				},
				{ label: __("Raised By"), key: "raised_by" },
				{ label: __("Amount"), key: "amount", align: "right", html: money },
			],
		});
	}

	// ------------------------------------------------------------ shift table

	render_shifts(shifts) {
		const money = (value) => format_currency(value, this.currency);
		const status_class = {
			[__("Balanced")]: "pdb-status-ok",
			[__("Short")]: "pdb-status-short",
			[__("Excess")]: "pdb-status-excess",
		};

		this.render_table(this.$shifts, {
			title: __("Shift Cash Reconciliation"),
			empty: __("No closed shifts in this period"),
			rows: shifts,
			columns: [
				{
					label: __("Shift"),
					key: "shift",
					html: (value) => this.link_cell("POS Closing Shift", value, value),
				},
				{ label: __("POS Profile"), key: "pos_profile" },
				{ label: __("Cashier"), key: "cashier" },
				{
					label: __("Closed On"),
					key: "period_end_date",
					html: (value) => frappe.datetime.str_to_user(value),
				},
				{ label: __("Opening"), key: "opening", align: "right", html: money },
				{ label: __("Expected"), key: "expected", align: "right", html: money },
				{ label: __("Closing"), key: "closing", align: "right", html: money },
				{ label: __("Difference"), key: "difference", align: "right", html: money },
				{ label: __("Deposited"), key: "deposit_amount", align: "right", html: money },
				{
					label: __("Status"),
					key: "status",
					html: (value) =>
						`<span class="pdb-status ${status_class[value] || ""}">${frappe.utils.escape_html(
							value
						)}</span>`,
				},
			],
		});
	}

	// ----------------------------------------------------------------- export

	export_ledger() {
		if (!this.data || !this.data.ledger.rows.length) {
			frappe.msgprint(__("Nothing to export for the selected filters"));
			return;
		}

		const fields = [
			"posting_date",
			"posting_time",
			"name",
			"customer_name",
			"cashier",
			"cost_center",
			"pos_profile",
			"modes",
			"total_qty",
			"base_grand_total",
			"base_discount_amount",
			"base_total_taxes_and_charges",
			"base_net_total",
			"outstanding_amount",
			"is_return",
		];

		const data = [fields.map((f) => frappe.model.unscrub(f))];
		this.data.ledger.rows.forEach((row) => {
			data.push(fields.map((f) => row[f]));
		});

		const filters = this.get_filters();
		frappe.tools.downloadify(data, null, `POS Day Book ${filters.from_date} to ${filters.to_date}`);
	}

	export_expenses() {
		const rows = this.data && this.data.expenses.rows.rows;
		if (!rows || !rows.length) {
			frappe.msgprint(__("Nothing to export for the selected filters"));
			return;
		}

		const fields = [
			"posting_date",
			"name",
			"accounts",
			"user_remark",
			"pos_profile",
			"shift",
			"raised_by",
			"amount",
		];

		const data = [fields.map((f) => frappe.model.unscrub(f))];
		rows.forEach((row) => data.push(fields.map((f) => row[f])));

		const filters = this.get_filters();
		frappe.tools.downloadify(
			data,
			null,
			`POS Expenses ${filters.from_date} to ${filters.to_date}`
		);
	}
};
