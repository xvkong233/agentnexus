import { useEffect, useState } from 'react'
import {
  Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag, Typography, message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import http, { fmtMoney } from '../../api/client'

export default function Tenants() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()
  const [op, setOp] = useState(null) // { type, tenant }
  const [opForm] = Form.useForm()

  const load = async (p = page) => {
    setLoading(true)
    try {
      const r = await http.get('/api/admin/tenants', { params: { keyword, status, page: p, page_size: 20 } })
      setItems(r.items)
      setTotal(r.total)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const doCreate = async () => {
    const values = await form.validateFields()
    await http.post('/api/admin/tenants', values)
    message.success('创建成功')
    setCreateOpen(false)
    form.resetFields()
    load(1)
  }

  const doOp = async () => {
    const values = await opForm.validateFields()
    await http.post(`/api/admin/tenants/${op.tenant.id}/${op.type}`, values)
    message.success('操作成功')
    setOp(null)
    opForm.resetFields()
    load()
  }

  const toggleStatus = async (row) => {
    await http.post(`/api/admin/tenants/${row.id}`, { status: row.status === 'active' ? 'suspended' : 'active' })
    load()
  }

  const columns = [
    { title: '编码', dataIndex: 'code', width: 140 },
    { title: '名称', dataIndex: 'name' },
    {
      title: '余额(¥)',
      width: 150,
      render: (_, r) => (
        <Space>
          <Typography.Text type={r.balance <= 0 ? 'danger' : 'success'} strong>
            {fmtMoney(r.balance, 2)}
          </Typography.Text>
          {r.blocked && <Tag color="error">已封锁</Tag>}
        </Space>
      ),
    },
    { title: '欠费阈值', width: 100, render: (_, r) => fmtMoney(r.low_balance_threshold, 2) },
    {
      title: '状态',
      width: 90,
      render: (_, r) => (
        <Tag color={r.status === 'active' ? 'success' : 'default'}>{r.status === 'active' ? '正常' : '停用'}</Tag>
      ),
    },
    { title: '联系人', dataIndex: 'contact_name', width: 100 },
    {
      title: '操作',
      width: 260,
      render: (_, r) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/admin/tenants/${r.id}`)}>
            详情
          </Button>
          <Button
            size="small"
            type="primary"
            variant="filled"
            color="green"
            onClick={() => {
              setOp({ type: 'recharge', tenant: r })
              opForm.setFieldsValue({ amount: 100, note: '' })
            }}
          >
            充值
          </Button>
          <Button size="small" onClick={() => { setOp({ type: 'adjust', tenant: r }); opForm.setFieldsValue({ amount: 0, note: '' }) }}>
            调整
          </Button>
          <Popconfirm title={`确认${r.status === 'active' ? '停用' : '启用'}该租户？`} onConfirm={() => toggleStatus(r)}>
            <Button size="small" danger={r.status === 'active'}>
              {r.status === 'active' ? '停用' : '启用'}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="搜索名称/编码"
          style={{ width: 220 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={() => load(1)}
          allowClear
        />
        <Select
          placeholder="状态"
          style={{ width: 120 }}
          value={status || undefined}
          onChange={(v) => setStatus(v || '')}
          allowClear
          options={[
            { value: 'active', label: '正常' },
            { value: 'suspended', label: '停用' },
          ]}
        />
        <Button type="primary" onClick={() => load(1)}>
          查询
        </Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新建租户
        </Button>
      </Space>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{ current: page, pageSize: 20, total, onChange: (p) => { setPage(p); load(p) }, showTotal: (t) => `共 ${t} 条` }}
      />

      <Modal
        title="新建租户"
        open={createOpen}
        onOk={doCreate}
        onCancel={() => setCreateOpen(false)}
        width={520}
        destroyOnHidden
      >
        <Form form={form} layout="horizontal" labelCol={{ span: 6 }} wrapperCol={{ span: 17 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="code" label="编码" rules={[{ required: true }]}>
            <Input placeholder="唯一编码，如 cust-a" />
          </Form.Item>
          <Form.Item name="contact_name" label="联系人">
            <Input />
          </Form.Item>
          <Form.Item name="contact_phone" label="联系电话">
            <Input />
          </Form.Item>
          <Form.Item name="low_balance_threshold" label="欠费阈值(¥)" initialValue={0}>
            <InputNumber min={0} precision={2} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item label={<b>门户账号（可选）</b>} colon={false}>
            <span />
          </Form.Item>
          <Form.Item name="portal_username" label="登录用户名">
            <Input placeholder="留空则不创建" />
          </Form.Item>
          <Form.Item name="portal_password" label="登录密码">
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>
          <Form.Item name="initial_balance" label="赠送余额(¥)" initialValue={0}>
            <InputNumber min={0} precision={2} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`${op?.type === 'recharge' ? '充值' : '余额调整'} - ${op?.tenant?.name || ''}`}
        open={!!op}
        onOk={doOp}
        onCancel={() => setOp(null)}
        width={420}
        destroyOnHidden
      >
        <Form form={opForm} layout="horizontal" labelCol={{ span: 7 }} wrapperCol={{ span: 15 }}>
          <Form.Item
            name="amount"
            label={op?.type === 'recharge' ? '充值金额' : '调整金额(带符号)'}
            rules={op?.type === 'recharge' ? [{ required: true, min: 0.01 }] : [{ required: true }]}
          >
            <InputNumber precision={2} style={{ width: 200 }} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
