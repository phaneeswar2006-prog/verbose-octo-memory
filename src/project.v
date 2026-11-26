`default_nettype none

module tt_um_deadtime_pwm (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

    // Tiny Tapeout bidirectional pins are unused.
    assign uio_out = 8'b00000000;
    assign uio_oe  = 8'b00000000;

    // Control mapping:
    // uio_in[1:0] = register select
    // uio_in[2]   = load enable
    // uio_in[3]   = PWM enable

    wire [1:0] reg_sel = uio_in[1:0];
    wire       load_en = uio_in[2];
    wire       pwm_en  = uio_in[3];

    // Shadow registers: software-programmed settings.
    reg [7:0] shadow_duty;
    reg [7:0] shadow_period;
    reg [3:0] shadow_dt;

    // Active registers: settings used by the PWM generator.
    reg [7:0] active_duty;
    reg [7:0] active_period;
    reg [3:0] active_dt;

    // PWM counter and period boundary.
    reg [7:0] counter;

    wire period_end = (counter >= active_period);
    wire raw_pwm   = pwm_en && (counter < active_duty);

    // -------------------------------------------------
    // 1. Shadow-register write interface
    // -------------------------------------------------

    always @(posedge clk) begin
        if (!rst_n) begin
            shadow_duty   <= 8'd10;
            shadow_period <= 8'd19;
            shadow_dt     <= 4'd3;
        end else if (load_en) begin
            case (reg_sel)
                2'b00: shadow_duty <= ui_in;

                2'b01:
                    shadow_period <=
                        (ui_in == 8'd0) ? 8'd1 : ui_in;

                2'b10:
                    shadow_dt <= ui_in[3:0];

                default: begin
                end
            endcase
        end
    end

    // -------------------------------------------------
    // 2. PWM counter and shadow-to-active transfer
    // -------------------------------------------------

    always @(posedge clk) begin
        if (!rst_n) begin
            counter       <= 8'd0;
            active_duty   <= 8'd10;
            active_period <= 8'd19;
            active_dt     <= 4'd3;
        end else if (!pwm_en) begin
            counter       <= 8'd0;
            active_duty   <= shadow_duty;
            active_period <= shadow_period;
            active_dt     <= shadow_dt;
        end else if (period_end) begin
            counter       <= 8'd0;

            // Atomic update at the period boundary.
            active_duty   <= shadow_duty;
            active_period <= shadow_period;
            active_dt     <= shadow_dt;
        end else begin
            counter <= counter + 8'd1;
        end
    end

    // -------------------------------------------------
    // 3. Complementary PWM with programmable dead-time
    // -------------------------------------------------

    reg [3:0] dead_cnt;
    reg       last_req_h;
    reg       pending_h;
    reg       initialized;

    reg       pwm_h_reg;
    reg       pwm_l_reg;

    // raw_pwm is the requested high-side state.
    // The low-side request is its complement.
    wire req_h = raw_pwm;

    always @(posedge clk) begin
        if (!rst_n || !ena || !pwm_en) begin
            dead_cnt   <= 4'd0;
            last_req_h <= 1'b0;
            pending_h  <= 1'b0;
            initialized <= 1'b0;

            pwm_h_reg <= 1'b0;
            pwm_l_reg <= 1'b0;

        end else if (!initialized) begin
            // Start safely with both outputs OFF.
            initialized <= 1'b1;
            last_req_h  <= req_h;
            pending_h   <= req_h;
            dead_cnt    <= active_dt;

            pwm_h_reg <= 1'b0;
            pwm_l_reg <= 1'b0;

        end else if (req_h != last_req_h) begin
            // Switching request changed:
            // turn both outputs OFF and start dead-time.
            last_req_h <= req_h;
            pending_h  <= req_h;
            dead_cnt   <= active_dt;

            pwm_h_reg <= 1'b0;
            pwm_l_reg <= 1'b0;

        end else if (dead_cnt != 4'd0) begin
            // Count down while both outputs remain OFF.
            pwm_h_reg <= 1'b0;
            pwm_l_reg <= 1'b0;

            if (dead_cnt == 4'd1) begin
                dead_cnt <= 4'd0;

                // Apply the pending state after the delay.
                pwm_h_reg <= pending_h;
                pwm_l_reg <= !pending_h;
            end else begin
                dead_cnt <= dead_cnt - 4'd1;
            end

        end else begin
            // Normal complementary operation.
            pwm_h_reg <= req_h;
            pwm_l_reg <= !req_h;
        end
    end

    // -------------------------------------------------
    // 4. Output mapping
    // -------------------------------------------------

    assign uo_out[0]   = pwm_h_reg;
    assign uo_out[1]   = pwm_l_reg;
    assign uo_out[2]   = raw_pwm;
    assign uo_out[3]   = period_end;
    assign uo_out[7:4] = 4'b0000;

    wire _unused = &{1'b0, uio_in[7:4]};

endmodule

`default_nettype wire

