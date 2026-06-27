report 71104 "MTM GT Draft Invoice"
{
    ApplicationArea = All;
    Caption = 'MTM GT Draft Invoice';
    DefaultRenderingLayout = MTMGTInvoiceStandard202606OnePage;
    PreviewMode = PrintLayout;
    UsageCategory = None;

    dataset
    {
        dataitem(SalesInvoiceHeader; "Sales Header")
        {
            DataItemTableView = where("Document Type" = const(Invoice));
            RequestFilterFields = "No.", "Bill-to Customer No.", "Sell-to Customer No.";

            column(No; "No.")
            {
            }
            column(Bill_to_Name; "Bill-to Name")
            {
            }
            column(Bill_to_Address; GetBillToAddress(SalesInvoiceHeader))
            {
            }
            column(serie; '')
            {
            }
            column(numero; "No.")
            {
            }
            column(Date_Time_Stamped; WorkDate())
            {
            }
            column(Fiscal_Invoice_Number_PAC; DraftFiscalTextLbl)
            {
            }
            column(Curp; GetCustomerNIT("Bill-to Customer No."))
            {
            }
            column(Divisa; GetCurrencyCode(SalesInvoiceHeader))
            {
            }
            column(Nombre_comercial; CompanyInformation.Name)
            {
            }
            column(Name; CompanyInformation.Name)
            {
            }
            column(Company_NIT; CompanyInformation."VAT Registration No.")
            {
            }
            column(Address; CompanyInformation.Address)
            {
            }
            column(Company_Address_2; CompanyInformation."Address 2")
            {
            }
            column(Company_City; CompanyInformation.City)
            {
            }
            column(Company_Post_Code; CompanyInformation."Post Code")
            {
            }
            column(Company_Pais; CompanyInformation."Country/Region Code")
            {
            }
            column(CompanyPicture; CompanyInformation.Picture)
            {
            }
            column(MontoTotalSinIva; MTMAmountExclVAT)
            {
            }
            column(MontoIVA; MTMVATAmount)
            {
            }
            column(TotalConIVA; MTMAmountInclVAT)
            {
            }
            column(SerieInterna; CopyStr("No.", 1, 5))
            {
            }
            column(NoInterno; "No.")
            {
            }
            column(TotalLetra; AmountToSpanishText(MTMAmountInclVAT))
            {
            }
            column(MTM_FEL_QR_Code; '')
            {
            }
            column(MTM_ISR_Comment; MTMISRComment)
            {
            }
            column(MTM_PO_Number; GetDraftPONumber(SalesInvoiceHeader))
            {
            }
            column(MTM_Booking_Label; GetDraftBookingLabel(SalesInvoiceHeader))
            {
            }
            column(MTM_Booking; GetDraftBooking(SalesInvoiceHeader))
            {
            }
            column(MTM_Containers_Label; GetDraftContainersLabel(SalesInvoiceHeader))
            {
            }
            column(MTM_Containers; GetDraftContainers(SalesInvoiceHeader))
            {
            }
            column(MTM_Invoice_Date_Text; FormatInvoiceDate("Posting Date"))
            {
            }

            dataitem(SalesInvoiceLine; "Sales Line")
            {
                DataItemLink = "Document Type" = field("Document Type"), "Document No." = field("No.");
                DataItemTableView = where(Type = filter(<> " "));

                column(Type; Format(Type))
                {
                }
                column(No_Item; "No.")
                {
                }
                column(Description; GetSalesLineInvoiceDescription(SalesInvoiceLine))
                {
                }
                column(MTM_Line_Description; GetSalesLineInvoiceDescription(SalesInvoiceLine))
                {
                }
                column(MTM_Line_Page_No; MTMLinePageNo)
                {
                }
                column(MTM_Line_Index_On_Page; MTMLineIndexOnPage)
                {
                }
                column(Quantity; Quantity)
                {
                }
                column(Unit_Price; "Unit Price")
                {
                }
                column(Line_Amount; "Line Amount")
                {
                }
                column(Amount_Including_VAT; "Amount Including VAT")
                {
                }
                column(UnitarioTotal; "Line Amount")
                {
                }

                trigger OnAfterGetRecord()
                begin
                    if IsMTMShipmentMetadataLine(GetSalesLineInvoiceDescription(SalesInvoiceLine)) then begin
                        CurrReport.Skip();
                        exit;
                    end;

                    MTMVisibleLineNo += 1;
                    MTMLinePageNo := ((MTMVisibleLineNo - 1) div 8) + 1;
                    MTMLineIndexOnPage := ((MTMVisibleLineNo - 1) mod 8) + 1;
                end;
            }

            trigger OnAfterGetRecord()
            begin
                Clear(MTMVisibleLineNo);
                Clear(MTMLinePageNo);
                Clear(MTMLineIndexOnPage);
                CompanyInformation.Get();
                CompanyInformation.CalcFields(Picture);
                CalculateDraftTotals(SalesInvoiceHeader);
                MTMISRComment := BuildISRComment(SalesInvoiceHeader);
            end;
        }
    }

    rendering
    {
        layout(MTMGTInvoiceStandard202606OnePage)
        {
            Type = RDLC;
            LayoutFile = './layouts/MTMGTDraftInvoice202605.rdl';
            Caption = 'MTM GT Invoice Standard 2026-06 One Page';
            Summary = 'Approved MTM Guatemala draft invoice layout for print and PDF output.';
        }
    }

    trigger OnPreReport()
    begin
        CompanyInformation.Get();
        CompanyInformation.CalcFields(Picture);
    end;

    var
        CompanyInformation: Record "Company Information";
        MTMAmountExclVAT: Decimal;
        MTMVATAmount: Decimal;
        MTMAmountInclVAT: Decimal;
        MTMISRComment: Text;
        MTMVisibleLineNo: Integer;
        MTMLinePageNo: Integer;
        MTMLineIndexOnPage: Integer;
        DraftFiscalTextLbl: Label 'BORRADOR - SIN CERTIFICAR', Locked = true;
        NATISRCommentLbl: Label 'SUJETO A PAGOS TRIMESTRALES ISR', Locked = true;
        INTISRCommentLbl: Label 'SUJETO A PAGOS TRIMESTRALES ISR. SERVICIOS NO AFECTOS. NO AFECTO AL IVA (FUERA DEL HECHO GENERADOR ART. 3, 7 Y 8, LEY DEL IVA).', Locked = true;

    local procedure CalculateDraftTotals(SalesHeader: Record "Sales Header")
    var
        SalesLine: Record "Sales Line";
    begin
        Clear(MTMAmountExclVAT);
        Clear(MTMAmountInclVAT);
        Clear(MTMVATAmount);

        SalesLine.SetRange("Document Type", SalesHeader."Document Type");
        SalesLine.SetRange("Document No.", SalesHeader."No.");
        SalesLine.SetFilter(Type, '<>%1', SalesLine.Type::" ");

        if SalesLine.FindSet() then
            repeat
                MTMAmountExclVAT += SalesLine."Line Amount";
                MTMAmountInclVAT += SalesLine."Amount Including VAT";
            until SalesLine.Next() = 0;

        MTMVATAmount := MTMAmountInclVAT - MTMAmountExclVAT;
    end;

    local procedure BuildISRComment(SalesHeader: Record "Sales Header"): Text
    var
        SalesLine: Record "Sales Line";
        LineNoPrefix: Text;
        HasNATLines: Boolean;
    begin
        SalesLine.SetRange("Document Type", SalesHeader."Document Type");
        SalesLine.SetRange("Document No.", SalesHeader."No.");
        SalesLine.SetFilter(Type, '<>%1', SalesLine.Type::" ");

        if not SalesLine.FindSet() then
            exit('');

        repeat
            LineNoPrefix := CopyStr(UpperCase(Format(SalesLine."No.")), 1, 3);
            if LineNoPrefix = 'INT' then
                exit(INTISRCommentLbl);
            if LineNoPrefix = 'NAT' then
                HasNATLines := true;
        until SalesLine.Next() = 0;

        if HasNATLines then
            exit(NATISRCommentLbl);

        exit('');
    end;

    local procedure GetBillToAddress(SalesHeader: Record "Sales Header"): Text
    begin
        exit(TrimText(SalesHeader."Bill-to Address" + ' ' + SalesHeader."Bill-to Address 2" + ' ' + SalesHeader."Bill-to City" + ' ' + SalesHeader."Bill-to Post Code" + ' ' + SalesHeader."Bill-to Country/Region Code"));
    end;

    local procedure GetCurrencyCode(SalesHeader: Record "Sales Header"): Code[10]
    begin
        if SalesHeader."Currency Code" <> '' then
            exit(SalesHeader."Currency Code");

        exit('GTQ');
    end;

    local procedure GetCustomerNIT(CustomerNo: Code[20]): Text
    var
        Customer: Record Customer;
    begin
        if Customer.Get(CustomerNo) then
            exit(Customer."VAT Registration No.");

        exit('');
    end;

    local procedure GetSalesLineInvoiceDescription(SalesLine: Record "Sales Line"): Text
    var
        SalesLineRef: RecordRef;
        FieldValue: Text;
        AccountDescription: Text;
    begin
        SalesLineRef.GetTable(SalesLine);
        FieldValue := GetCustomInvoiceDescription(SalesLineRef);
        if FieldValue <> '' then
            exit(FieldValue);

        if SalesLine.Description <> '' then
            exit(SalesLine.Description);

        AccountDescription := GetTrackedAccountDescription(SalesLine."No.");
        if AccountDescription <> '' then
            exit(AccountDescription);

        exit(SalesLine.Description);
    end;

    local procedure GetCustomInvoiceDescription(RecordRef: RecordRef): Text
    var
        FieldRef: FieldRef;
        FieldIndex: Integer;
        FieldValue: Text;
    begin
        for FieldIndex := 1 to RecordRef.FieldCount() do begin
            FieldRef := RecordRef.FieldIndex(FieldIndex);
            if (FieldRef.Name() = 'Descripción Factura') or
               (FieldRef.Caption() = 'Descripción Factura') or
               (FieldRef.Name() = 'Description XL') or
               (FieldRef.Caption() = 'Description XL')
            then begin
                FieldValue := DelChr(Format(FieldRef.Value()), '<>', ' ');
                if FieldValue <> '' then
                    exit(FieldValue);
            end;
        end;

        exit('');
    end;

    local procedure GetTrackedAccountDescription(AccountNo: Code[20]): Text
    var
        Item: Record Item;
        GLAccount: Record "G/L Account";
        AccountPrefix: Text;
    begin
        AccountPrefix := CopyStr(UpperCase(Format(AccountNo)), 1, 3);
        if not (AccountPrefix in ['INT', 'NAT']) then
            exit('');

        if Item.Get(AccountNo) then
            if Item.Description <> '' then
                exit(UpperCase(Item.Description));

        if GLAccount.Get(AccountNo) then
            exit(UpperCase(GLAccount.Name));

        exit('');
    end;

    local procedure GetDraftPONumber(SalesHeader: Record "Sales Header"): Text
    begin
        if SalesHeader."Your Reference" <> '' then
            exit(SalesHeader."Your Reference");

        if SalesHeader."External Document No." <> '' then
            exit(SalesHeader."External Document No.");

        exit(SalesHeader."Your Reference");
    end;

    local procedure FormatInvoiceDate(InvoiceDate: Date): Text
    begin
        if InvoiceDate = 0D then
            exit('');

        exit(Format(InvoiceDate, 0, '<Day,2>/<Month,2>/<Year4>'));
    end;

    local procedure GetDraftBooking(SalesHeader: Record "Sales Header"): Text
    var
        BookingValue: Text;
    begin
        if IsDraftAirShipment(SalesHeader) then
            exit(GetDraftAirwayBill(SalesHeader));

        BookingValue := GetDraftLineMarkerValue(SalesHeader, 'BOOKING NO.', 'CONTAINER');
        if BookingValue <> '' then
            exit(BookingValue);

        exit(GetDraftLineMarkerValue(SalesHeader, 'BOOKING', 'CONTAINER'));
    end;

    local procedure GetDraftBookingLabel(SalesHeader: Record "Sales Header"): Text
    begin
        if IsDraftAirShipment(SalesHeader) then
            exit('AWB:');

        exit('BOOKING:');
    end;

    local procedure GetDraftContainers(SalesHeader: Record "Sales Header"): Text
    var
        ContainerValue: Text;
    begin
        if IsDraftAirShipment(SalesHeader) then
            exit('');

        ContainerValue := GetDraftLineMarkerValues(SalesHeader, 'CONTAINER NUMBER');
        if ContainerValue <> '' then
            exit(ContainerValue);

        ContainerValue := GetDraftLineMarkerValues(SalesHeader, 'CONTAINERS');
        if ContainerValue <> '' then
            exit(ContainerValue);

        exit(GetDraftLineMarkerValues(SalesHeader, 'CONTAINER'));
    end;

    local procedure GetDraftContainersLabel(SalesHeader: Record "Sales Header"): Text
    begin
        if IsDraftAirShipment(SalesHeader) then
            exit('');

        exit('CONTENEDORES:');
    end;

    local procedure IsDraftAirShipment(SalesHeader: Record "Sales Header"): Boolean
    var
        ProductValue: Text;
    begin
        ProductValue := UpperCase(GetDraftLineMarkerValue(SalesHeader, 'PRODUCT', ''));
        exit((ProductValue = 'AIR') or (ProductValue = 'AEREO'));
    end;

    local procedure GetDraftAirwayBill(SalesHeader: Record "Sales Header"): Text
    var
        AirwayBillValue: Text;
    begin
        AirwayBillValue := GetDraftLineMarkerValue(SalesHeader, 'AWB', '');
        if AirwayBillValue <> '' then
            exit(AirwayBillValue);

        exit(GetDraftLineMarkerValue(SalesHeader, 'AIRWAY BILL', ''));
    end;

    local procedure GetDraftLineMarkerValues(SalesHeader: Record "Sales Header"; Marker: Text): Text
    var
        SalesLine: Record "Sales Line";
        MarkerValue: Text;
        CombinedValue: Text;
    begin
        SalesLine.SetRange("Document Type", SalesHeader."Document Type");
        SalesLine.SetRange("Document No.", SalesHeader."No.");

        if not SalesLine.FindSet() then
            exit('');

        repeat
            MarkerValue := ExtractMarkerValue(GetSalesLineInvoiceDescription(SalesLine), Marker, '');
            if MarkerValue <> '' then begin
                if CombinedValue <> '' then
                    CombinedValue := CombinedValue + ', ';
                CombinedValue := CopyStr(CombinedValue + MarkerValue, 1, 250);
            end;
        until SalesLine.Next() = 0;

        exit(CombinedValue);
    end;

    local procedure GetDraftLineMarkerValue(SalesHeader: Record "Sales Header"; Marker: Text; NextMarker: Text): Text
    var
        SalesLine: Record "Sales Line";
        MarkerValue: Text;
    begin
        SalesLine.SetRange("Document Type", SalesHeader."Document Type");
        SalesLine.SetRange("Document No.", SalesHeader."No.");

        if not SalesLine.FindSet() then
            exit('');

        repeat
            MarkerValue := ExtractMarkerValue(GetSalesLineInvoiceDescription(SalesLine), Marker, NextMarker);
            if MarkerValue <> '' then
                exit(CopyStr(MarkerValue, 1, 250));
        until SalesLine.Next() = 0;

        exit('');
    end;

    local procedure IsMTMShipmentMetadataLine(LineDescription: Text): Boolean
    begin
        exit(CopyStr(UpperCase(LineDescription), 1, 8) = 'MTM META');
    end;

    local procedure ExtractMarkerValue(SourceText: Text; Marker: Text; NextMarker: Text): Text
    var
        UpperSourceText: Text;
        UpperValueText: Text;
        ValueText: Text;
        MarkerPosition: Integer;
        StopPosition: Integer;
    begin
        UpperSourceText := UpperCase(SourceText);
        MarkerPosition := StrPos(UpperSourceText, Marker);
        if MarkerPosition = 0 then
            exit('');

        ValueText := CopyStr(SourceText, MarkerPosition + StrLen(Marker));
        ValueText := DelChr(ValueText, '<>', ' :#.-');

        if NextMarker <> '' then begin
            UpperValueText := UpperCase(ValueText);
            StopPosition := StrPos(UpperValueText, NextMarker);
            if StopPosition > 1 then
                ValueText := CopyStr(ValueText, 1, StopPosition - 1);
        end;

        exit(DelChr(ValueText, '<>', ' '));
    end;

    local procedure AmountToSpanishText(Amount: Decimal): Text
    var
        WholeAmount: Integer;
        Cents: Integer;
    begin
        WholeAmount := Amount div 1;
        Cents := Round((Amount - WholeAmount) * 100, 1);

        exit(UpperCase(NumberToSpanish(WholeAmount) + ' CON ' + PadStr('', 2 - StrLen(Format(Cents)), '0') + Format(Cents) + '/100'));
    end;

    local procedure NumberToSpanish(Number: Integer): Text
    var
        Thousands: Integer;
        Remainder: Integer;
    begin
        if Number = 0 then
            exit('cero');

        if Number < 1000 then
            exit(NumberBelowThousandToSpanish(Number));

        Thousands := Number div 1000;
        Remainder := Number mod 1000;

        if Thousands = 1 then
            if Remainder = 0 then
                exit('mil')
            else
                exit('mil ' + NumberBelowThousandToSpanish(Remainder));

        if Remainder = 0 then
            exit(NumberBelowThousandToSpanish(Thousands) + ' mil');

        exit(NumberBelowThousandToSpanish(Thousands) + ' mil ' + NumberBelowThousandToSpanish(Remainder));
    end;

    local procedure NumberBelowThousandToSpanish(Number: Integer): Text
    var
        Hundreds: Integer;
        Remainder: Integer;
    begin
        if Number < 100 then
            exit(NumberBelowHundredToSpanish(Number));

        if Number = 100 then
            exit('cien');

        Hundreds := Number div 100;
        Remainder := Number mod 100;

        case Hundreds of
            1:
                exit('ciento ' + NumberBelowHundredToSpanish(Remainder));
            2:
                exit(JoinSpanish('doscientos', Remainder));
            3:
                exit(JoinSpanish('trescientos', Remainder));
            4:
                exit(JoinSpanish('cuatrocientos', Remainder));
            5:
                exit(JoinSpanish('quinientos', Remainder));
            6:
                exit(JoinSpanish('seiscientos', Remainder));
            7:
                exit(JoinSpanish('setecientos', Remainder));
            8:
                exit(JoinSpanish('ochocientos', Remainder));
            9:
                exit(JoinSpanish('novecientos', Remainder));
        end;
    end;

    local procedure NumberBelowHundredToSpanish(Number: Integer): Text
    var
        Tens: Integer;
        Units: Integer;
    begin
        case Number of
            0:
                exit('');
            1:
                exit('uno');
            2:
                exit('dos');
            3:
                exit('tres');
            4:
                exit('cuatro');
            5:
                exit('cinco');
            6:
                exit('seis');
            7:
                exit('siete');
            8:
                exit('ocho');
            9:
                exit('nueve');
            10:
                exit('diez');
            11:
                exit('once');
            12:
                exit('doce');
            13:
                exit('trece');
            14:
                exit('catorce');
            15:
                exit('quince');
            16:
                exit('dieciseis');
            17:
                exit('diecisiete');
            18:
                exit('dieciocho');
            19:
                exit('diecinueve');
            20:
                exit('veinte');
        end;

        Tens := Number div 10;
        Units := Number mod 10;

        if Number < 30 then
            exit('veinti' + NumberBelowHundredToSpanish(Units));

        case Tens of
            3:
                exit(JoinTens('treinta', Units));
            4:
                exit(JoinTens('cuarenta', Units));
            5:
                exit(JoinTens('cincuenta', Units));
            6:
                exit(JoinTens('sesenta', Units));
            7:
                exit(JoinTens('setenta', Units));
            8:
                exit(JoinTens('ochenta', Units));
            9:
                exit(JoinTens('noventa', Units));
        end;
    end;

    local procedure JoinSpanish(Prefix: Text; Remainder: Integer): Text
    begin
        if Remainder = 0 then
            exit(Prefix);

        exit(Prefix + ' ' + NumberBelowHundredToSpanish(Remainder));
    end;

    local procedure JoinTens(Prefix: Text; Units: Integer): Text
    begin
        if Units = 0 then
            exit(Prefix);

        exit(Prefix + ' y ' + NumberBelowHundredToSpanish(Units));
    end;

    local procedure TrimText(Value: Text): Text
    begin
        exit(DelChr(Value, '<>', ' '));
    end;
}
