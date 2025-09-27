// API客户端 - 处理HTTP POST请求
class APIClient {
    constructor() {
        this.baseURL = '';
        this.timeout = 10000;
    }

    async request(endpoint, data = {}, method = 'POST') {
        let url = endpoint;
        const options = {
            method: method,
            headers: {},
            signal: AbortSignal.timeout(this.timeout)
        };

        try {
            if (method === 'GET' && Object.keys(data).length > 0) {
                url += '?' + new URLSearchParams(data).toString();
            }
            const response = await fetch(url, options);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API请求失败:', error);
            throw error;
        }
    }

    async getStockPrice(symbol, startDate, endDate) {
        const params = {
            symbol,
            start_date: startDate,
            end_date: endDate
        };
        return this.request('/api/stock/price', params, 'GET');
    }

    async getFundamentalData(symbol) {
        const params = { symbol };
        return this.request('/api/stock/fundamental', params, 'GET');
    }

    async getStockNews(symbol, daysBack = 30) {
        const params = {
            symbol,
            days_back: daysBack
        };
        return this.request('/api/stock/news', params, 'GET');
    }

    async sendMessage(message) {
        return this.request('/api/message', message);
    }

    async getHealth() {
        return this.request('/health', {}, 'GET');
    }
}

// 创建全局API客户端实例
window.apiClient = new APIClient();