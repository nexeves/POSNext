<template>
	<Dialog
		v-model="open"
		:options="{
			title: __('Expense Entry'),
			size: 'lg',
		}"
	>
		<template #body-content>
			<div class="flex flex-col gap-4">

				<div>
					<label class="block text-sm font-medium mb-1">
						{{ __('Expense Account') }}
					</label>

					<select
						v-model="expense_account"
						class="w-full border rounded px-3 py-2"
					>
						<option value="">
							{{ __('Select Expense Account') }}
						</option>

						<option
							v-for="account in expenseAccounts"
							:key="account"
							:value="account"
						>
							{{ account }}
						</option>
					</select>
				</div>

				<div>
					<label class="block text-sm font-medium mb-1">
						{{ __('Mode of Payment') }}
					</label>

					<select
						v-model="mode_of_payment"
						class="w-full border rounded px-3 py-2"
					>
						<option value="">
							{{ __('Select Mode of Payment') }}
						</option>

						<option
							v-for="mop in modeOfPayments"
							:key="mop"
							:value="mop"
						>
							{{ mop }}
						</option>
					</select>
				</div>

				<Input
					type="number"
					v-model="amount"
					:placeholder="__('Amount')"
				/>

				<textarea
					v-model="remarks"
					class="w-full border rounded px-3 py-2"
					rows="3"
					:placeholder="__('Remarks')"
				/>
			</div>
		</template>

		<template #actions>
			<div class="flex justify-end gap-2 w-full">
				<Button
					variant="subtle"
					@click="open = false"
				>
					{{ __('Cancel') }}
				</Button>

				<Button
					theme="blue"
					@click="saveExpense"
					:loading="saveExpenseResource.loading"
				>
					{{ __('Save') }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import {
	Dialog,
	Button,
	Input,
	createResource,
} from "frappe-ui";

import { useToast } from "../composables/useToast";

const { showSuccess, showWarning } = useToast();

const props = defineProps({
	modelValue: {
		type: Boolean,
		default: false,
	},
	openingShift: {
		type: String,
		default: "",
	},
	posProfile: {
		type: String,
		default: "",
	},
});

const emit = defineEmits(["update:modelValue"]);

const open = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
});

const expense_account = ref("");
const mode_of_payment = ref("");
const amount = ref("");
const remarks = ref("");

const expenseAccounts = ref([]);
const modeOfPayments = ref([]);

const saveExpenseResource = createResource({
	url: "pos_next.api.expense_entry.create_expense_entry",
	auto: false,
});

const expenseAccountsResource = createResource({
	url: "pos_next.api.expense_entry.get_expense_accounts",
	auto: false,
});

const modeOfPaymentsResource = createResource({
	url: "pos_next.api.expense_entry.get_pos_profile_mops",
	auto: false,
});

watch(
	() => open.value,
	async (value) => {
		if (value) {
			await loadDropdowns();
		}
	}
);

async function loadDropdowns() {
	try {
		const accounts =
			await expenseAccountsResource.submit();

		expenseAccounts.value = accounts || [];

		const mops =
			await modeOfPaymentsResource.submit({
				pos_profile: props.posProfile,
			});

		modeOfPayments.value = mops || [];
	} catch (error) {
		console.error(error);

		showWarning(
			__("Failed to load Expense Accounts / Modes of Payment")
		);
	}
}

async function saveExpense() {
	try {
		if (!expense_account.value) {
			showWarning(
				__("Please select Expense Account")
			);
			return;
		}

		if (!mode_of_payment.value) {
			showWarning(
				__("Please select Mode of Payment")
			);
			return;
		}

		if (!amount.value || Number(amount.value) <= 0) {
			showWarning(
				__("Please enter a valid Amount")
			);
			return;
		}

		const response =
			await saveExpenseResource.submit({
				data: {
					opening_shift: props.openingShift,
					pos_profile: props.posProfile,
					expense_account: expense_account.value,
					mode_of_payment: mode_of_payment.value,
					amount: amount.value,
					remarks: remarks.value,
				},
			});

		showSuccess(
			__(
				"Expense Entry Created: {0}",
				[
					response?.journal_entry ||
					"Journal Entry",
				]
			)
		);

		expense_account.value = "";
		mode_of_payment.value = "";
		amount.value = "";
		remarks.value = "";

		open.value = false;
	} catch (error) {
		console.error(error);

		showWarning(
			error?.messages?.[0] ||
			error?.message ||
			__("Failed to create Expense Entry")
		);
	}
}
</script>