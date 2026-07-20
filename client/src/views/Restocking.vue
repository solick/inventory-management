<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <div class="budget-header">
          <label for="budget-slider" class="budget-label">{{ t('restocking.budgetLabel') }}</label>
          <span class="budget-value">{{ currencySymbol }}{{ Math.round(budget).toLocaleString() }}</span>
        </div>
        <input
          id="budget-slider"
          type="range"
          class="budget-slider"
          min="0"
          :max="maxBudget"
          :step="sliderStep"
          v-model.number="budget"
        />
        <div class="budget-range-labels">
          <span>{{ currencySymbol }}0</span>
          <span>{{ currencySymbol }}{{ maxBudget.toLocaleString() }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.recommendedSpend') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ Math.round(recommendedSpend).toLocaleString() }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ Math.round(remainingBudget).toLocaleString() }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.itemsRecommended') }}</div>
          <div class="stat-value">{{ recommendations.length }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }}</h3>
        </div>
        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="rec in recommendations" :key="rec.item_sku">
                <td><strong>{{ rec.item_sku }}</strong></td>
                <td>{{ rec.item_name }}</td>
                <td>
                  <span :class="['badge', rec.trend]">
                    {{ t(`trends.${rec.trend}`) }}
                  </span>
                </td>
                <td>{{ rec.quantity }}</td>
                <td>{{ currencySymbol }}{{ rec.unit_cost.toLocaleString() }}</td>
                <td><strong>{{ currencySymbol }}{{ rec.lineTotal.toLocaleString() }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="order-footer">
          <span class="lead-time-note">{{ t('restocking.leadTimeNote', { days: 14 }) }}</span>
          <button
            class="po-button create"
            :disabled="recommendations.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="successMessage" class="confirmation-banner success-banner">
          {{ successMessage }}
        </div>
        <div v-if="submitError" class="confirmation-banner error-banner">
          {{ submitError }}
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(0)
    const submitting = ref(false)
    const successMessage = ref(null)
    const submitError = ref(null)

    const trendRank = { increasing: 0, stable: 1, decreasing: 2 }

    // Every item's full shortfall cost, used to size the budget slider
    const totalShortfallCost = computed(() => {
      return forecasts.value.reduce((sum, f) => {
        const shortfall = Math.max(f.forecasted_demand - f.current_demand, 0)
        return sum + shortfall * f.unit_cost
      }, 0)
    })

    const maxBudget = computed(() => Math.ceil(totalShortfallCost.value))

    const sliderStep = computed(() => {
      if (maxBudget.value <= 0) return 100
      const step = Math.round(maxBudget.value / 100)
      return step > 0 ? step : 1
    })

    const recommendations = computed(() => {
      const shortfalls = forecasts.value
        .map(f => ({
          item_sku: f.item_sku,
          item_name: f.item_name,
          trend: f.trend,
          unit_cost: f.unit_cost,
          shortfall: Math.max(f.forecasted_demand - f.current_demand, 0)
        }))
        .filter(f => f.shortfall > 0)
        .sort((a, b) => {
          const rankDiff = trendRank[a.trend] - trendRank[b.trend]
          if (rankDiff !== 0) return rankDiff
          return b.shortfall - a.shortfall
        })

      const results = []
      let runningTotal = 0

      for (const item of shortfalls) {
        const lineCost = item.shortfall * item.unit_cost

        if (runningTotal + lineCost <= budget.value) {
          results.push({
            item_sku: item.item_sku,
            item_name: item.item_name,
            trend: item.trend,
            quantity: item.shortfall,
            unit_cost: item.unit_cost,
            lineTotal: lineCost
          })
          runningTotal += lineCost
        } else {
          const partialQuantity = Math.floor((budget.value - runningTotal) / item.unit_cost)
          if (partialQuantity >= 1) {
            const lineTotal = partialQuantity * item.unit_cost
            results.push({
              item_sku: item.item_sku,
              item_name: item.item_name,
              trend: item.trend,
              quantity: partialQuantity,
              unit_cost: item.unit_cost,
              lineTotal
            })
            runningTotal += lineTotal
          }
          break
        }
      }

      return results
    })

    const recommendedSpend = computed(() => {
      return recommendations.value.reduce((sum, r) => sum + r.lineTotal, 0)
    })

    const remainingBudget = computed(() => budget.value - recommendedSpend.value)

    const loadForecasts = async () => {
      try {
        loading.value = true
        error.value = null
        forecasts.value = await api.getDemandForecasts()
        budget.value = Math.round(maxBudget.value / 2)
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      submitting.value = true
      successMessage.value = null
      submitError.value = null
      try {
        const items = recommendations.value.map(r => ({
          sku: r.item_sku,
          name: r.item_name,
          quantity: r.quantity,
          unit_price: r.unit_cost
        }))
        const order = await api.createOrder({ items, lead_time_days: 14 })
        successMessage.value = t('restocking.orderSuccess', { orderNumber: order.order_number })
      } catch (err) {
        submitError.value = t('restocking.orderError')
        console.error(err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      loading,
      error,
      budget,
      maxBudget,
      sliderStep,
      recommendations,
      recommendedSpend,
      remainingBudget,
      currencySymbol,
      submitting,
      successMessage,
      submitError,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  margin-bottom: 1.5rem;
}

.budget-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.75rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.budget-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.budget-slider {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(90deg, #3b82f6, #e2e8f0);
  appearance: none;
  -webkit-appearance: none;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #ff7a59;
  border: 3px solid white;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
  cursor: pointer;
  transition: transform 0.15s ease;
}

.budget-slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #ff7a59;
  border: 3px solid white;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
  cursor: pointer;
  transition: transform 0.15s ease;
}

.budget-slider::-moz-range-thumb:hover {
  transform: scale(1.1);
}

.budget-slider::-moz-range-progress {
  background: #ff7a59;
  border-radius: 999px;
  height: 8px;
}

.budget-range-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: #94a3b8;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.order-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid #f1f5f9;
  gap: 1rem;
}

.lead-time-note {
  font-size: 0.813rem;
  color: #64748b;
}

.po-button {
  padding: 0.625rem 1.25rem;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.po-button.create {
  background: #3b82f6;
  color: white;
}

.po-button.create:hover:not(:disabled) {
  background: #2563eb;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);
}

.po-button.create:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.confirmation-banner {
  margin-top: 1rem;
  padding: 0.875rem 1rem;
  border-radius: 8px;
  font-size: 0.875rem;
}

.success-banner {
  background: #d1fae5;
  border: 1px solid #a7f3d0;
  color: #065f46;
}

.error-banner {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
}
</style>
