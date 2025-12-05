/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService, useListener } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
const actionRegistry = registry.category("actions");
import { rpc } from "@web/core/network/rpc";
import { Component, useRef, useState, onWillStart,useEffect } from "@odoo/owl";
/**
 * WooDashBoard component for displaying WooCommerce-related statistics and data,
 * including orders, products, customers, and instances, in Odoo's dashboard interface.
 * It integrates with WooCommerce through Odoo models to fetch and display key data in the form
 * of graphs and tables, and provides search functionality for filtering order and product lists.
 */
class WooDashBoard extends Component {
    async setup() {
        super.setup(...arguments);
        this.state = useState({
             order_outputs: [],
             product_outputs: [],
             instance_count : 0,
             products_count: 0,
             customers_count: 0,
             orders_count:0,
        });
        this.orm = useService("orm");
        this.root = useRef('root');
        this.graph = useRef('graph');
        this.actionService = useService("action");
        this.render_orders_table();
        this.render_products();
         useEffect(()=>{
            this.render_tile();
            this.render_product_category();
            this.render_instance();
            this.tile_graphs();
        })
        }
         /**
     * Fetches and renders the tile statistics for instances, products, customers, and orders.
     * It calls the Odoo model to get these statistics and updates the component's state accordingly.
     */
        render_tile() {
            var def1 =  this.orm.call('sale.order','get_tile_details',[]
            ).then((result) => {
               if (this.root.el.querySelector('.instance_right')){
                  this.state.instance_count = result.instance
               }
               if (this.root.el.querySelector('.product_right')){
                  this.state.products_count = result.products
               }
               if (this.root.el.querySelector('.partner_right')){
                  this.state.customers_count = result.partners
               }
               if (this.root.el.querySelector('.order_right')){
                  this.state.orders_count = result.orders
               }
            });
          }
         /**
     * Fetches and renders the orders table by calling the 'sale.order' model in Odoo.
     * It populates the state with order data, which is then displayed in the table.
     */
        render_orders_table(){
            var def1 =  this.orm.call('sale.order','get_orders',[]
            ).then((result) =>  {
            this.state.order_outputs = result;
            });
          }
          /**
     * Fetches and renders the products table by calling the 'product.template' model in Odoo.
     * It populates the state with product data, which is then displayed in the table.
     */
        render_products(){
            this.orm.call('product.template', 'get_product_graph',[]
            ).then((result)  => {
                this.state.product_outputs = result;
            });
          }
          /**
     * Fetches and renders the product category chart (doughnut) by calling the 'product.public.category' model.
     * It handles showing or hiding the chart based on the availability of product data.
     */
          render_product_category(){
            this.orm.call('product.public.category','get_product_category_graph',[]
            ).then((result) => {
            var canvasElement = this.graph.el.querySelector("#category_canvas");
        var messageDiv = this.graph.el.querySelector("#no_data_message");
        if (result.products_count.length === 0) {
            // Hide the canvas and show the message div if there's no data
            canvasElement.style.display = 'none';
            messageDiv.style.display = 'block';
        } else {
            // Show the canvas and hide the message div if there's data
            messageDiv.style.display = 'none';
            canvasElement.style.display = 'block';
                var ctx =  this.graph.el.querySelector("#category_canvas");
                var myChart = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: result.categories_name,//x axis
                        datasets: [{
                            label: 'Count', // Name the series
                            data: result.products_count, // Specify the data values array
                            backgroundColor: [
                                "#003f5c",
                                "#2f4b7c",
                                "#f95d6a",
                                "#665191",
                                "#d45087",
                                "#ff7c43",
                                "#ffa600",
                                "#a05195",
                                "#6d5c16",
                                "#dc3545",
                                "#1995ad",
                                "#317773",
                                "#1995ad",
                                "#9a9eab",
                                "#007bff",
                                "#20c997",
                                "#BCC6CC",
                                "#4682B4",
                                 "#7B68EE",
                                "#FF007F",
                                "#800020",
                                "#FFEF00",
                                "#FF5A36",
                                "#082567",
                            ],
                            borderColor: [
                                "#003f5c",
                                "#2f4b7c",
                                "#f95d6a",
                                "#665191",
                                "#d45087",
                                "#ff7c43",
                                "#ffa600",
                                "#a05195",
                                "#6d5c16",
                                "#dc3545",
                                "#1995ad",
                                "#317773",
                                "#1995ad",
                                "#9a9eab",
                                "#007bff",
                                "#20c997",
                            ],
                            barPercentage: 0.5,
                            barThickness: 6,
                            maxBarThickness: 8,
                            minBarLength: 0,
                            borderWidth: 1, // Specify bar border width
                            type: 'doughnut', // Set this data to a line chart
                            fill: false
                        }]
                    },
                    options: {
                        scales: {
                            y: {
                                beginAtZero: true
                            },
                        },
                        responsive: true, // Instruct chart js to respond nicely.
                        maintainAspectRatio: false, // Add to prevent default behaviour of full-width/height
                    }
                });
                }
            });
      }
      render_instance(){
        this.orm.call('woo.commerce.instance',"get_instance_graph",[]
        ).then((result) => {
            var ctx = this.graph.el.querySelector("#customers_canvas")
            var myChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: result.instance_name,//x axis
                    datasets: [
                            {
                                label: "Products",
                                backgroundColor: "#A7226E",
                                data: result.product_len
                            },
                            {
                                label: "Customers",
                                backgroundColor: "#EC2049",
                                data: result.customer_len
                            },
                            {
                                label: "Orders",
                                backgroundColor: "#2F9599",
                                data: result.order_len
                            }
                        ]
                },
                options: {
                    scales: {
                        y: {
                            beginAtZero: true
                        },
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                }
            });
        });
      }
      /**
     * Renders a static bar chart for customers across months (for illustrative purposes).
     */
      tile_graphs(){
            var dataBar = {
          labels: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"],
          datasets: [{
            label: 'Customers',
            data: [5, 10, 15, 12, 10, 8, 6, 4],
            backgroundColor: [
              '#dee5ef',
              '#dee5ef',
              '#dee5ef',
              '#dee5ef',
              '#fc381d',
              '#dee5ef',
              '#dee5ef',
              '#dee5ef',
            ],
            borderColor: [
              '#dee5ef',
              '#dee5ef',
              '#dee5ef',
              '#dee5ef',
              '#fc381d',
              '#dee5ef',
              '#dee5ef',
              '#dee5ef',
            ],
            borderWidth: 1,
            fill: false
          }]
        };
        var optionsBar = {
          scales: {
            yAxes: [{
              ticks: {
                beginAtZero: true,
                display: false,

              },
              gridLines: {
                display: false,
                drawBorder: false
              }
            }],
            xAxes: [{
              ticks: {
                beginAtZero: true,
                display: false,
              },
              gridLines: {
                display: false,
                drawBorder: false
              }
            }]
          },
          legend: {
            display: false
          },
          elements: {
            point: {
              radius: 0
            }
          },
          tooltips: {
            enabled: false
          }

        };
        }
      onclick_instance(ev) {
            ev.stopPropagation();
            var options = {
                on_reverse_breadcrumb: this.on_reverse_breadcrumb,
            };
            this.actionService.doAction({
                name: _t("Instance"),
                type: 'ir.actions.act_window',
                res_model: 'woo.commerce.instance',
                view_mode: 'tree,form,calendar',
                views: [[false, 'list'],[false, 'form']],
                target: 'current',
            }, options)
        }
      onclick_product(ev) {
            ev.stopPropagation();
            var options = {
                on_reverse_breadcrumb: this.on_reverse_breadcrumb,
            };
            this.actionService.doAction({
                name: _t("Product"),
                type: 'ir.actions.act_window',
                res_model: 'product.template',
                view_mode: 'tree,form,calendar',
                views: [[false, 'list'],[false, 'form']],
                domain: [['woo_id', '!=', false]],
                target: 'current',
            }, options)
        }
      onclick_customer(ev) {
            ev.stopPropagation();
            var options = {
                on_reverse_breadcrumb: this.on_reverse_breadcrumb,
            };
            this.actionService.doAction({
                name: _t("Customers"),
                type: 'ir.actions.act_window',
                res_model: 'res.partner',
                view_mode: 'tree,form,calendar',
                views: [[false, 'list'],[false, 'form']],
                domain: [['instance_id', '!=', false]],
                target: 'current',
            }, options)
        }
    /**
     * Handles the click event for navigating to the WooCommerce instance records.
     */
      onclick_orders(ev) {
            ev.stopPropagation();
            var options = {
                on_reverse_breadcrumb: this.on_reverse_breadcrumb,
            };
            this.actionService.doAction({
                name: _t("Orders"),
                type: 'ir.actions.act_window',
                res_model: 'sale.order',
                view_mode: 'tree,form,calendar',
                views: [[false, 'list'],[false, 'form']],
                domain: [['woo_id', '!=', false]],
                target: 'current',
            }, options)
        }
         /**
     * Handles the click event for navigating to the WooCommerce product records.
     */
        onclick_product_search() {
            var input, filter, table, tr, td, i, txtValue;
              input = document.getElementById("product_search");
              filter = input.value.toUpperCase();
              table = document.getElementById("product_table");
              tr = table.getElementsByTagName("tr");
              for (i = 0; i < tr.length; i++) {
                td = tr[i].getElementsByTagName("td")[0];
                if (td) {
                  txtValue = td.textContent || td.innerText;
                  if (txtValue.toUpperCase().indexOf(filter) > -1) {
                    tr[i].style.display = "";
                  } else {
                    tr[i].style.display = "none";
                  }
                }
              }
        }
         /**
     * Handles the click event for navigating to the WooCommerce customer records.
     */
        onclick_order_search() {
            var input, filter, table, tr, td, i, txtValue;
              input = document.getElementById("order_search");
              filter = input.value.toUpperCase();
              table = document.getElementById("orders_table");
              tr = table.getElementsByTagName("tr");
              for (i = 0; i < tr.length; i++) {
                td = tr[i].getElementsByTagName("td")[0];
                if (td) {
                  txtValue = td.textContent || td.innerText;
                  if (txtValue.toUpperCase().indexOf(filter) > -1) {
                    tr[i].style.display = "";
                  } else {
                    tr[i].style.display = "none";
                  }
                }
              }
        }
        /**
     * Handles the click event for navigating to the WooCommerce order records.
     */
        onclick_order_row(ev){
            var order_id = ev.target.innerHTML;
            var options = {
                on_reverse_breadcrumb: this.on_reverse_breadcrumb,
            };
            this.actionService.doAction({
                name: _t("Order"),
                type: 'ir.actions.act_window',
                res_model: 'sale.order',
                view_mode: 'form',
                views: [[false, 'list'],[false, 'form']],
                domain: [['name', '=', order_id]],
                target: 'current',
            }, options)
        }
}
WooDashBoard.template = 'Woocommercedashboard';
actionRegistry.add("woocommerce_dashboard_tag", WooDashBoard);
