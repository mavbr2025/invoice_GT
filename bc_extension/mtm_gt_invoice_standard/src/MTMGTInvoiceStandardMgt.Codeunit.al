codeunit 71102 "MTM GT Invoice Std. Mgt."
{
    procedure ApplyInvoiceLayoutRouting()
    var
        Setup: Codeunit "MTM GT Invoice Std. Setup";
    begin
        Setup.ApplyInvoiceLayoutRouting();
    end;
}
