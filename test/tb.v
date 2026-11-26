
`default_nettype none
`timescale 1ns / 1ps

module tb;

    reg         clk;
    reg         rst_n;
    reg         ena;
    reg  [7:0]  ui_in;
    reg  [7:0]  uio_in;

    wire [7:0]  uo_out;
    wire [7:0]  uio_out;
    wire [7:0]  uio_oe;

    // Gate-level power pins, required by the template
`ifdef GL_TEST
    wire VPWR = 1'b1;
    wire VGND = 1'b0;
`endif

    // Instantiate the actual project module
    tt_um_phaneeswar2006_prog uut (
`ifdef GL_TEST
        .VPWR(VPWR),
        .VGND(VGND),
`endif
        .ui_in(ui_in),
        .uo_out(uo_out),
        .uio_in(uio_in),
        .uio_out(uio_out),
        .uio_oe(uio_oe),
        .ena(ena),
        .clk(clk),
        .rst_n(rst_n)
    );

    initial begin
        $dumpfile("tb.fst");
        $dumpvars(0, tb);
        #1;
    end

    initial clk = 1'b0;
    always #10 clk = ~clk;

endmodule

`default_nettype wire
